# 003: App ingress

Stage: S0 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Allow public IPv4 traffic to Traefik on TCP port 80 via `0.0.0.0/0`. Security group references restrict database and host-to-host traffic to designated lab services.

## Rejected alternative

Allow port 80 only from the student’s and grader’s IPv4 CIDRs.

## Why

Public ingress makes the S0 app reachable for grading and demos from changing client IPs. The trade-off is that any IPv4 client can call the app’s HTTP endpoints.

## What would show this was wrong

Revisit the scope if public traffic interferes with the demo, or if the app begins handling data or features that require restricted access.
