# Sales Oriented Prompt Design

## Goal

Improve product name and keyword generation so the LLM optimizes for Korean ecommerce search exposure, click-through, and purchase conversion while keeping the existing JSON response contract.

## Scope

- Keep output keys unchanged: `product_name`, `keywords`, `review_reason`.
- Keep category and `마이카테` fields out of the product-keyword flow.
- Strengthen the prompt with sales/search rules:
  - prioritize strong shopping intent
  - combine representative, long-tail, use-case, location, and buyer intent keywords
  - avoid unrelated broad keywords
  - avoid fake brands/specs/effects
  - use standard Korean in product names and reserve common typo variants for keywords only

## Testing

Tests verify the generated request prompt includes ecommerce SEO, sales volume, search exposure, purchase conversion, keyword prioritization, and anti-overclaim rules.
