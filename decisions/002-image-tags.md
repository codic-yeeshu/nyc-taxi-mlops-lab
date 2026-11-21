# 002: Image tags and rollback

Stage: S0 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Tag each GHCR app image with the full Git commit SHA. To identify an image for rollback, use the SHA of the last known-good deployment.

## Rejected alternative

Use the image digest as the deploy and rollback reference.

## Why

The full SHA ties the image tag directly to source and lets us compare the deployed `/version` response against GitHub’s commit. A digest identifies the exact image bytes, but it needs a separate mapping to the source commit.

## What would show this was wrong

Revisit the scheme if rebuilding a commit changes the image behind an existing tag and we need rollback to recover the exact previous image.
