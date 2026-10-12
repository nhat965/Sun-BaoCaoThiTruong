# News pipeline

The metadata-only pipeline is:

`COLLECT → VALIDATE → NORMALIZE → DEDUPLICATE → ENTITY RESOLUTION → EVENT CLASSIFICATION → EVIDENCE STORAGE`.

`RssNewsConnector` implements the connector boundary. Feed URLs are configured through `NEWS_FEEDS`; only feeds that return a valid RSS response count as operational. Article bodies are never downloaded. Stored rows include source, source URL, collection time, publication time, title, related ticker, relevance, event category, group hash, evidence and uncertainty.

VnExpress is the default configured feed. Vietstock, CafeF, exchange disclosures and IR feeds require an authorized URL/API and are not represented as live until a real request succeeds.
