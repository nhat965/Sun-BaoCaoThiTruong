"""store normalized, deduplicated news metadata and event groups"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=True),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("normalized_title", sa.String(1024), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("relevance_score", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("event_category", sa.String(32), nullable=False, server_default="other"),
        sa.Column("event_summary", sa.Text(), nullable=True),
        sa.Column("facts_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("implications_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("uncertainty_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("group_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("source_name", "url", name="uq_news_source_url"),
    )
    op.create_index("ix_news_articles_security_id", "news_articles", ["security_id"])
    op.create_index("ix_news_articles_source_name", "news_articles", ["source_name"])
    op.create_index("ix_news_articles_normalized_title", "news_articles", ["normalized_title"])
    op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"])
    op.create_index("ix_news_articles_event_category", "news_articles", ["event_category"])
    op.create_index("ix_news_articles_group_hash", "news_articles", ["group_hash"])
    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("securities.id"), nullable=True),
        sa.Column("group_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("event_category", sa.String(32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_news_events_security_id", "news_events", ["security_id"])
    op.create_index("ix_news_events_group_hash", "news_events", ["group_hash"])
    op.create_index("ix_news_events_event_category", "news_events", ["event_category"])

def downgrade():
    op.drop_table("news_events")
    op.drop_table("news_articles")
