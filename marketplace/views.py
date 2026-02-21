from django.db import models # <--- Added this for Chat queries
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny # <--- Added AllowAny here
from rest_framework.response import Response
from .models import Product, Offer, ChatMessage
from api.serializers import ProductSerializer, ChatMessageSerializer, OfferSerializer

@api_view(['GET'])
@permission_classes([AllowAny]) # Anyone can see products
def list_products(request):
    """ Shows all products for the Shopping System """
    products = Product.objects.all().order_by('-created_at')
    return Response(ProductSerializer(products, many=True).data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_product(request):
    data = request.data
    # Accessing keys properly
    product = Product.objects.create(
        seller=request.user,
        title=data['title'],
        description=data['description'],
        price=data['price'],
        condition=data.get('condition', 'New'),
        pic_1=request.FILES.get('pic_1'), 
        pic_2=request.FILES.get('pic_2'),
        pic_3=request.FILES.get('pic_3')
    )
    return Response(ProductSerializer(product).data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_offer(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return Response({"error": "Product not found"}, status=404)

    offer_price = request.data.get('offered_price')
    offer = Offer.objects.create(
        product=product,
        buyer=request.user,
        offered_price=offer_price
    )
    return Response({"status": "Offer sent!", "offer": OfferSerializer(offer).data})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_offers(request):
    """ Shows offers received by the seller for their products """
    # Offers where I am the seller of the product
    offers = Offer.objects.filter(product__seller=request.user)
    return Response(OfferSerializer(offers, many=True).data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manage_offer(request, offer_id):
    """ Seller Accepts or Rejects an offer """
    try:
        offer = Offer.objects.get(id=offer_id)
    except Offer.DoesNotExist:
        return Response({"error": "Offer not found"}, status=404)
        
    # Security check: Only the seller of the product can manage the offer
    if request.user != offer.product.seller:
        return Response({"error": "Not authorized"}, status=403)
        
    action = request.data.get('action') # 'Accepted' or 'Rejected'
    if action in ['Accepted', 'Rejected']:
        offer.status = action
        offer.save()
        return Response({"status": f"Offer {action}", "offer": OfferSerializer(offer).data})
    
    return Response({"error": "Invalid action"}, status=400)

@api_view(['POST', 'GET'])
@permission_classes([IsAuthenticated])
def product_chat(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return Response({"error": "Product not found"}, status=404)
    
    if request.method == 'POST':
        message_text = request.data.get('message')
        # Logic: If I am the seller, sending to buyer. If I am buyer, sending to seller.
        receiver = product.seller if request.user != product.seller else None
        
        if not receiver:
             # If seller is replying, we need to know WHICH buyer they are replying to
             buyer_id = request.data.get('buyer_id')
             if buyer_id:
                 from users.models import CustomUser
                 receiver = CustomUser.objects.get(id=buyer_id)
             else:
                 return Response({"error": "Buyer ID required for seller reply"}, status=400)
             
        msg = ChatMessage.objects.create(
            sender=request.user,
            receiver=receiver,
            product=product,
            message=message_text
        )
        return Response(ChatMessageSerializer(msg).data)
        
    elif request.method == 'GET':
        # Get all chats regarding this product where user is involved
        chats = ChatMessage.objects.filter(product=product).filter(
            models.Q(sender=request.user) | models.Q(receiver=request.user)
        )
        return Response(ChatMessageSerializer(chats.order_by('timestamp'), many=True).data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_chats(request):
    """ Inbox: List of unique conversations for the user """
    # Get all messages where user is sender or receiver
    messages = ChatMessage.objects.filter(
        models.Q(sender=request.user) | models.Q(receiver=request.user)
    ).order_by('-timestamp')
    
    # Logic to group by 'Product' and 'Other Person'
    conversations = {}
    for msg in messages:
        # Identify who the 'other' person is in the chat
        other_user = msg.receiver if msg.sender == request.user else msg.sender
        
        # Unique key for this conversation (Product + Other User)
        key = f"{msg.product.id}_{other_user.id}"
        
        if key not in conversations:
            conversations[key] = {
                "product_id": msg.product.id,
                "product_title": msg.product.title,
                "other_user_name": other_user.first_name,
                "other_user_id": other_user.id,
                "last_message": msg.message,
                "timestamp": msg.timestamp
            }
            
    return Response(list(conversations.values()))