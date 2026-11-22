# 010: How serving loads a promoted model

Stage: S3 · Date: 2026-11-22 · Author: YEESHU · Drafted by agent: yes

## Choice

After GitHub approves a promotion, move the champion alias and hot-reload the champion container. Verify the loaded version with a prediction through the public app.

## Rejected alternative

Restart the champion container for every promotion.

## Why

Hot reload lets the previous model keep answering while the new model loads. The first promotion begins from the app's static fallback. A container restart clears process state, but it can send riders to the fallback while serving starts.

## What would show this was wrong

Revisit if loading a second model alongside the first exhausts app-host memory or if repeated reloads leave the process unhealthy.
