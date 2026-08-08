# Apify SEO internal linking (orchestration)

Python scripts that batch-crawl blog URLs with the [scrapegraph-deepseek](https://github.com/Manojaditya64/scrapegraph-deepseek) Apify Actor and merge validated `blog_profile` JSON for an internal linking pipeline.

**Flow:** URL list → Apify Actor (`blog_profile` preset) → merge profiles → (separate Node linker) suggest verbatim anchors per draft.

Companion article: [How we built an Apify Actor for blog profiling and internal link suggestions](https://github.com/Manojaditya64/apify-seo-internal-linking) (Apify Content Program draft in `apify-article-seo-internal-linking.md`).

## Setup

```bash
cp .env.example .env
# Add APIFY_API_TOKEN
cp data/urls.example.txt data/urls.txt
# Edit data/urls.txt with your client's blog URLs
```

No pip dependencies (stdlib + `urllib`).

## Crawl + merge profiles

```bash
python crawl_blog_profiles.py --dry-run
python crawl_blog_profiles.py --batch-size 10
python crawl_blog_profiles.py --merge-only data/crawl-results-2026-03-04.json
```

Default batch size is **10 URLs per Apify run** so one bad URL does not block a 50-URL job.

Outputs:

- `data/crawl-results-YYYY-MM-DD.json` — raw Actor dataset rows
- `data/blog-profiles.json` — merged slug → profile map (only `status: success` rows)

## Actor

| Role | Actor | Link |
|------|-------|------|
| Crawl + blog profile | scrapegraph-deepseek (ours) | [Console](https://console.apify.com/actors/chEKCbZsaOZlufvd5) (`chEKCbZsaOZlufvd5`) |

Actor source: https://github.com/Manojaditya64/scrapegraph-deepseek

Set `DEEPSEEK_API_KEY` on the Actor **Source → Environment variables** tab in Apify Console.

## Runtime linker (not in this repo)

The full linker (chunking, topic pools, pgvector retrieval, gated LLM anchor pick) runs in a separate Node service. This repo covers the **Apify ingest** layer only. See the article for architecture and quality gates.

## License

ISC
