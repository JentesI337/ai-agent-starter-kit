# E-Commerce Agent System Design

## Core Conversation States

1. **Product Discovery**
   - User Intent: "Find me blue sneakers under $100"
   - NLU Triggers: Entity extraction for product type, color, price range
   - Backend Operations: Call product search API with filters
   - Agent Response: "I found 5 blue sneakers under $100. Would you like to see them?"

2. **Cart Management**
   - User Intent: "Add 2 shirts to my cart"
   - NLU Triggers: Quantity and action recognition
   - Backend Operations: POST /cart/add-item with productId and quantity
   - Agent Response: "Added 2 shirts to your cart. Total is now $40."

3. **Checkout Initiation**
   - User Intent: "I'm ready to checkout"
   - NLU Triggers: Transactional keyword detection
   - Backend Operations: GET /checkout/session to retrieve or create session
   - Agent Response: "Let's start checkout. Please confirm your shipping address."

4. **Order Confirmation**
   - User Intent: "Place order"
   - NLU Triggers: Action commitment signal
   - Backend Operations: POST /orders with final cart contents and payment details
   - Agent Response: "Your order #12345 has been placed successfully! Estimated delivery in 3 days."

## Product Search Logic

- Query Parser supports entities: category (shoes), brand (Nike), price (<$100), color (blue)
- Integrated with Elasticsearch-based catalog API
- Returns ranked results with confidence scores and fallback recommendations

## Cart Lifecycle Management

- Supports natural commands: "remove last item", "update quantity to 3"
- Real-time sync via WebSocket connection to e-commerce backend
- Handles out-of-stock scenarios gracefully with alternative suggestions

## Checkout Flow & Error Handling

1. Address Selection → Prompt if multiple saved addresses exist
2. Payment Method Verification → Retry mechanism for declined cards
3. Confirmation Prompt → Summarize items, cost, delivery estimate

Error Cases:
- Out of stock: Suggest similar items or notify when available
- Promo Code Invalid: Explain why and offer alternatives
- Payment Declined: Guide through updating card info securely

## Contextual Continuity

- Session persistence across platforms using JWT tokens
- Natural handoff points: Offer live chat when complexity exceeds bot scope
- Voice-to-text compatibility layer enables cross-channel interaction