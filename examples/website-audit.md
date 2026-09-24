# Website audit

A fan-out/fan-in audit: crawl first, run independent audits in parallel,
then roll everything up into one summary.

## Crawl sitemap
Fetch the sitemap and list every URL with its HTTP status code.
Flag redirects chains and 404s.

## Lighthouse audit
depends: crawl-sitemap
Run Lighthouse performance, SEO, and best-practices audits on the
10 highest-traffic pages from the crawl. Record scores.

## Accessibility check
depends: crawl-sitemap
Run automated axe-core checks on the homepage, pricing page, and
checkout flow. List violations by WCAG severity.

## Security headers scan
depends: crawl-sitemap
Check security headers (CSP, HSTS, X-Frame-Options) on the main
domain and note what's missing.

## Write summary
depends: lighthouse-audit, accessibility-check, security-headers-scan
Combine all findings into a prioritized fix list, ranked by
user impact vs. implementation effort. Keep it under one page.
