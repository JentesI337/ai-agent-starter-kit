When designing or analyzing e-commerce systems, apply these domain reasoning patterns:

**Conversion Funnel Analysis**
Trace the user journey from landing page through product discovery, cart addition, checkout, and payment confirmation. At each step, identify friction points: How many clicks/taps to complete the action? What information is requested and is it all necessary at this stage? What happens on failure (payment declined, out of stock, validation error) — does the user lose their progress? Measure or estimate drop-off at each funnel stage. Optimize the highest-drop-off stages first. Common conversion killers: mandatory account creation before checkout, surprise shipping costs, slow page loads, and unclear error messages.

**Inventory Consistency**
E-commerce systems must handle concurrent access to inventory. Analyze: What happens when two users simultaneously try to buy the last item? Is inventory decremented optimistically (risk of overselling) or pessimistically (risk of under-selling)? For reserved inventory: What is the reservation timeout? What happens if payment processing takes longer than the reservation? Are inventory counts eventually consistent across read replicas, and if so, what is the staleness window? Displaying "In Stock" when the item is actually sold out is a customer-hostile experience.

**Cart Race Conditions**
Shopping carts are stateful and long-lived — they are a primary source of consistency bugs. Analyze: What happens when a price changes while the item is in a user's cart? What happens when a promotion expires mid-checkout? Are carts stored server-side (persistent but requires session management) or client-side (simpler but vulnerable to tampering)? For server-side carts: Is the cart cleaned up on session expiry? Can a user have multiple active carts? Is the cart locked during checkout to prevent concurrent modifications?

**Pricing Engine Correctness**
Pricing logic is often the most complex part of an e-commerce system. Verify: Are discounts applied in the correct order (percentage discounts before fixed, or vice versa)? Can discount stacking create negative prices? Are tax calculations applied after discounts? Is currency handling using integer cents (not floating-point)? Are promotional codes validated server-side, not just client-side? Check for price manipulation: Can a user modify the price in the request payload, or is the price always looked up server-side?

**SEO & Structured Data**
For product pages, verify: Are Schema.org Product markup, breadcrumbs, and aggregate ratings correctly implemented? Is content rendered server-side (or SSR/SSG) for crawler accessibility? Are canonical URLs set to prevent duplicate content from URL parameters (filters, sorting, pagination)? Are product images optimized with descriptive alt text? Check Core Web Vitals: LCP < 2.5s (critical for product images), CLS < 0.1 (layout shifts from loading images/prices), FID < 100ms.