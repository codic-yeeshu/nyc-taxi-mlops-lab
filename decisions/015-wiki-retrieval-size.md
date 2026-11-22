# 015: Wiki chunks and retrieval size

Stage: S6 · Date: 2026-11-22 · Author: YEESHU · Drafted by agent: yes

## Choice

Use up to 220 estimated tokens per chunk, 32 tokens of overlap when splitting, and retrieve the closest three chunks by cosine distance.

## Rejected alternative

Use 160 tokens, 24 tokens of overlap, and retrieve two chunks.

## Why

The instructor wiki had 16 published pages. Body sizes were approximately 88 tokens at the median, 139 at the 90th percentile, and 181 at the maximum. With title and headings included, 220 tokens kept all 16 pages intact. The 160-token setting split one page and produced 17 chunks. Top three can supply another policy excerpt when a question needs context across pages. The three largest chunks total about 465 estimated tokens before prompt framing. The extra context uses CPU time during prompt processing.

## What would show this was wrong

Compare top two and top three on wiki-only questions. Revisit top three if its extra excerpt increases latency without improving answer accuracy or source coverage. Revisit overlap when the wiki has pages long enough to split with the chosen size.
