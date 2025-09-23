"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2024-07-01 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("current_plan", sa.String(), server_default=sa.text("'free'"), nullable=True),
        sa.Column("plan_expires_at", sa.DateTime(), nullable=True),
        sa.Column("total_minutes_transcribed", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("minutes_used_this_month", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_reset_date", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("total_generations", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("generations_used_this_month", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("minutes_per_month", sa.Float(), nullable=True),
        sa.Column("max_file_size_mb", sa.Float(), server_default=sa.text("100.0"), nullable=True),
        sa.Column("price_rub", sa.Float(), server_default=sa.text("0"), nullable=True),
        sa.Column("price_usd", sa.Float(), server_default=sa.text("0"), nullable=True),
        sa.Column("price_stars", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("features", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_plans_name"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_type", sa.String(), nullable=False),
        sa.Column("amount_rub", sa.Float(), nullable=True),
        sa.Column("amount_usd", sa.Float(), nullable=True),
        sa.Column("amount_stars", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("provider_payment_charge_id", sa.String(), nullable=True),
        sa.Column("telegram_payment_charge_id", sa.String(), nullable=True),
        sa.Column("external_payment_id", sa.String(), nullable=True),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_transactions_users"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"], unique=False)
    op.create_index("ix_transactions_provider_payment_charge_id", "transactions", ["provider_payment_charge_id"], unique=False)
    op.create_index("ix_transactions_telegram_payment_charge_id", "transactions", ["telegram_payment_charge_id"], unique=False)
    op.create_index("ix_transactions_external_payment_id", "transactions", ["external_payment_id"], unique=False)

    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("file_size_mb", sa.Float(), nullable=False),
        sa.Column("audio_duration_minutes", sa.Float(), nullable=False),
        sa.Column("raw_transcript", sa.Text(), nullable=True),
        sa.Column("formatted_transcript", sa.Text(), nullable=True),
        sa.Column("transcript_length", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("transcription_service", sa.String(), server_default=sa.text("'deepinfra'"), nullable=True),
        sa.Column("formatting_service", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("processing_time_seconds", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_transcriptions_users"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcriptions_user_id", "transcriptions", ["user_id"], unique=False)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("minutes_limit", sa.Float(), nullable=True),
        sa.Column("minutes_used", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_api_keys_users"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"], unique=False)

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("plan_type", sa.String(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("max_uses", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("current_uses", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("bonus_type", sa.String(), nullable=True),
        sa.Column("bonus_value", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_promo_codes_code"),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"], unique=True)

    op.create_table(
        "promo_activations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], name="fk_promo_activations_promo_codes"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_promo_activations_users"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_promo_activations_user_id", "promo_activations", ["user_id"], unique=False)
    op.create_index("ix_promo_activations_promo_code_id", "promo_activations", ["promo_code_id"], unique=False)

    op.create_table(
        "referral_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_referral_links_code"),
    )
    op.create_index("ix_referral_links_user_telegram_id", "referral_links", ["user_telegram_id"], unique=False)

    op.create_table(
        "referral_visits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_code", sa.String(), nullable=False),
        sa.Column("visitor_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referral_visits_referral_code", "referral_visits", ["referral_code"], unique=False)
    op.create_index("ix_referral_visits_visitor_telegram_id", "referral_visits", ["visitor_telegram_id"], unique=False)

    op.create_table(
        "referral_attribution",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("visitor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_code", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visitor_telegram_id", name="uq_referral_attribution_visitor_telegram_id"),
    )
    op.create_index("ix_referral_attribution_referral_code", "referral_attribution", ["referral_code"], unique=False)

    op.create_table(
        "referral_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_code", sa.String(), nullable=False),
        sa.Column("payer_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_rub", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referral_payments_referral_code", "referral_payments", ["referral_code"], unique=False)
    op.create_index("ix_referral_payments_payer_telegram_id", "referral_payments", ["payer_telegram_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_referral_payments_payer_telegram_id", table_name="referral_payments")
    op.drop_index("ix_referral_payments_referral_code", table_name="referral_payments")
    op.drop_table("referral_payments")

    op.drop_index("ix_referral_attribution_referral_code", table_name="referral_attribution")
    op.drop_table("referral_attribution")

    op.drop_index("ix_referral_visits_visitor_telegram_id", table_name="referral_visits")
    op.drop_index("ix_referral_visits_referral_code", table_name="referral_visits")
    op.drop_table("referral_visits")

    op.drop_index("ix_referral_links_user_telegram_id", table_name="referral_links")
    op.drop_table("referral_links")

    op.drop_index("ix_promo_activations_promo_code_id", table_name="promo_activations")
    op.drop_index("ix_promo_activations_user_id", table_name="promo_activations")
    op.drop_table("promo_activations")

    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_table("promo_codes")

    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("ix_transcriptions_user_id", table_name="transcriptions")
    op.drop_table("transcriptions")

    op.drop_index("ix_transactions_external_payment_id", table_name="transactions")
    op.drop_index("ix_transactions_telegram_payment_charge_id", table_name="transactions")
    op.drop_index("ix_transactions_provider_payment_charge_id", table_name="transactions")
    op.drop_index("ix_transactions_user_id", table_name="transactions")
    op.drop_table("transactions")

    op.drop_table("plans")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
