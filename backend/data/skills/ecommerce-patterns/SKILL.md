---
name: ecommerce-patterns
description: >
  Designs and reviews e-commerce systems including catalogs, checkout flows,
  order processing, inventory management, and SEO optimization.
requires_bins: []
os: any
user_invocable: true
---

# E-Commerce Design Patterns

## When to Apply
- Product catalog / PIM / DAM modeling
- Shopping cart and checkout flow implementation
- Order lifecycle and fulfillment pipelines
- Pricing engines, discounts, promotions
- Inventory management and stock synchronization
- SEO and structured data (Schema.org) markup

## Checklist

### Catalog & Product Modeling
- [ ] Product-variant hierarchy (e.g., SKU → Color → Size)
- [ ] Category tree with breadcrumb navigation support
- [ ] Faceted search / filter model defined
- [ ] Multi-currency and multi-language support
- [ ] Product bundles and cross-sell/upsell relationships

### Cart & Checkout
- [ ] Cart stored server-side with session/user binding
- [ ] Cart abandonment tracking and recovery flow
- [ ] Price recalculation on every cart mutation
- [ ] Shipping cost estimation before final checkout
- [ ] Guest checkout supported alongside account creation
- [ ] Idempotent order submission (double-click protection)

### Order Processing
- [ ] Order state machine with clear transitions (pending → paid → shipped → delivered)
- [ ] Event-driven architecture (CQRS/ES) for order mutations
- [ ] Webhook integration for fulfillment and shipping providers
- [ ] Partial fulfillment and split-shipment support
- [ ] Return/refund workflow with inventory restock

### Inventory Management
- [ ] Real-time stock level synchronization
- [ ] Reservation system (soft-lock during checkout)
- [ ] Back-in-stock notifications
- [ ] Multi-warehouse inventory allocation
- [ ] Safety stock thresholds with alerts

### Pricing & Promotions
- [ ] Rule-based pricing engine (quantity discounts, tiered pricing)
- [ ] Coupon codes with validation rules (single-use, expiry, min order)
- [ ] Flash sale / time-limited pricing support
- [ ] Price history for analytics and compliance

### SEO & Structured Data
- [ ] Schema.org Product, Offer, BreadcrumbList markup
- [ ] Canonical URLs for product variants
- [ ] Meta title / description templates per category
- [ ] Performance budget: LCP < 2.5s, CLS < 0.1, FID < 100ms
- [ ] Image optimization (WebP/AVIF, lazy loading, srcset)
- [ ] Sitemap.xml with product URLs and lastmod dates

## Output Format
```
## Commerce Architecture
Catalog, checkout, order-processing overview.

## Findings
| # | Area | Impact | Finding | Recommendation |
|---|---|---|---|---|

## SEO Assessment
Structured data compliance and performance metrics.

## Implementation Plan
Prioritized improvements with effort estimates.
```
