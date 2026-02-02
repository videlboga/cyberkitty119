--
-- PostgreSQL database dump
--

\restrict Xu1hN2eNWuC8tZVELcbmKlh2DXy9nUu1nl0YEggvuXSkKFQ6iLE6JXHdgMy4bRR

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO transkribator;

--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.api_keys (
    id integer NOT NULL,
    user_id integer NOT NULL,
    key_hash character varying NOT NULL,
    name character varying,
    minutes_limit double precision,
    minutes_used double precision DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_used_at timestamp without time zone,
    expires_at timestamp without time zone
);


ALTER TABLE public.api_keys OWNER TO transkribator;

--
-- Name: api_keys_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.api_keys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.api_keys_id_seq OWNER TO transkribator;

--
-- Name: api_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.api_keys_id_seq OWNED BY public.api_keys.id;


--
-- Name: events; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.events (
    id integer NOT NULL,
    user_id integer NOT NULL,
    kind character varying NOT NULL,
    payload text,
    ts timestamp without time zone
);


ALTER TABLE public.events OWNER TO transkribator;

--
-- Name: events_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.events_id_seq OWNER TO transkribator;

--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.events_id_seq OWNED BY public.events.id;


--
-- Name: google_credentials; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.google_credentials (
    id integer NOT NULL,
    user_id integer NOT NULL,
    access_token character varying NOT NULL,
    refresh_token character varying,
    expiry timestamp without time zone,
    scopes text,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE public.google_credentials OWNER TO transkribator;

--
-- Name: google_credentials_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.google_credentials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.google_credentials_id_seq OWNER TO transkribator;

--
-- Name: google_credentials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.google_credentials_id_seq OWNED BY public.google_credentials.id;


--
-- Name: note_chunks; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.note_chunks (
    id integer NOT NULL,
    note_id integer NOT NULL,
    user_id integer NOT NULL,
    chunk_index integer NOT NULL,
    text text NOT NULL,
    embedding public.vector(1536) NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.note_chunks OWNER TO transkribator;

--
-- Name: note_chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.note_chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.note_chunks_id_seq OWNER TO transkribator;

--
-- Name: note_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.note_chunks_id_seq OWNED BY public.note_chunks.id;


--
-- Name: note_group_links; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.note_group_links (
    note_id integer NOT NULL,
    group_id integer NOT NULL
);


ALTER TABLE public.note_group_links OWNER TO transkribator;

--
-- Name: note_groups; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.note_groups (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying NOT NULL,
    color character varying,
    tags jsonb DEFAULT '[]'::jsonb,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.note_groups OWNER TO transkribator;

--
-- Name: note_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.note_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.note_groups_id_seq OWNER TO transkribator;

--
-- Name: note_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.note_groups_id_seq OWNED BY public.note_groups.id;


--
-- Name: note_versions; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.note_versions (
    id integer NOT NULL,
    note_id integer NOT NULL,
    version integer NOT NULL,
    title character varying,
    markdown text NOT NULL,
    meta jsonb,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.note_versions OWNER TO transkribator;

--
-- Name: note_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.note_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.note_versions_id_seq OWNER TO transkribator;

--
-- Name: note_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.note_versions_id_seq OWNED BY public.note_versions.id;


--
-- Name: notes; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.notes (
    id integer NOT NULL,
    user_id integer NOT NULL,
    ts timestamp without time zone NOT NULL,
    source character varying,
    text text NOT NULL,
    summary text,
    type_hint character varying,
    type_confidence double precision,
    tags jsonb,
    links jsonb,
    drive_file_id character varying,
    status character varying DEFAULT 'ingested'::character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    raw_link character varying,
    current_version integer DEFAULT 0 NOT NULL,
    draft_title character varying,
    draft_md text,
    drive_path character varying,
    sheet_row_id character varying,
    meta jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE public.notes OWNER TO transkribator;

--
-- Name: notes_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notes_id_seq OWNER TO transkribator;

--
-- Name: notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.notes_id_seq OWNED BY public.notes.id;


--
-- Name: plans; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.plans (
    id integer NOT NULL,
    name character varying NOT NULL,
    display_name character varying NOT NULL,
    minutes_per_month double precision,
    max_file_size_mb double precision DEFAULT 100.0,
    price_rub double precision DEFAULT 0,
    price_usd double precision DEFAULT 0,
    price_stars integer DEFAULT 0,
    description text,
    features text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.plans OWNER TO transkribator;

--
-- Name: plans_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.plans_id_seq OWNER TO transkribator;

--
-- Name: plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.plans_id_seq OWNED BY public.plans.id;


--
-- Name: processing_jobs; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.processing_jobs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    note_id integer,
    job_type character varying(50) NOT NULL,
    status character varying(32) DEFAULT 'queued'::character varying NOT NULL,
    payload json,
    progress integer,
    attempts integer DEFAULT 0 NOT NULL,
    locked_by character varying(64),
    locked_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    started_at timestamp without time zone,
    finished_at timestamp without time zone,
    error text
);


ALTER TABLE public.processing_jobs OWNER TO transkribator;

--
-- Name: processing_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.processing_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.processing_jobs_id_seq OWNER TO transkribator;

--
-- Name: processing_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.processing_jobs_id_seq OWNED BY public.processing_jobs.id;


--
-- Name: promo_activations; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.promo_activations (
    id integer NOT NULL,
    user_id integer NOT NULL,
    promo_code_id integer NOT NULL,
    activated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone
);


ALTER TABLE public.promo_activations OWNER TO transkribator;

--
-- Name: promo_activations_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.promo_activations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.promo_activations_id_seq OWNER TO transkribator;

--
-- Name: promo_activations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.promo_activations_id_seq OWNED BY public.promo_activations.id;


--
-- Name: promo_codes; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.promo_codes (
    id integer NOT NULL,
    code character varying NOT NULL,
    plan_type character varying NOT NULL,
    duration_days integer,
    max_uses integer DEFAULT 1 NOT NULL,
    current_uses integer DEFAULT 0 NOT NULL,
    description character varying,
    bonus_type character varying,
    bonus_value character varying,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone
);


ALTER TABLE public.promo_codes OWNER TO transkribator;

--
-- Name: promo_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.promo_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.promo_codes_id_seq OWNER TO transkribator;

--
-- Name: promo_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.promo_codes_id_seq OWNED BY public.promo_codes.id;


--
-- Name: referral_attribution; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.referral_attribution (
    id integer NOT NULL,
    visitor_telegram_id bigint NOT NULL,
    referral_code character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.referral_attribution OWNER TO transkribator;

--
-- Name: referral_attribution_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.referral_attribution_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.referral_attribution_id_seq OWNER TO transkribator;

--
-- Name: referral_attribution_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.referral_attribution_id_seq OWNED BY public.referral_attribution.id;


--
-- Name: referral_links; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.referral_links (
    id integer NOT NULL,
    user_telegram_id bigint NOT NULL,
    code character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.referral_links OWNER TO transkribator;

--
-- Name: referral_links_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.referral_links_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.referral_links_id_seq OWNER TO transkribator;

--
-- Name: referral_links_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.referral_links_id_seq OWNED BY public.referral_links.id;


--
-- Name: referral_payments; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.referral_payments (
    id integer NOT NULL,
    referral_code character varying NOT NULL,
    payer_telegram_id bigint NOT NULL,
    amount_rub double precision NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.referral_payments OWNER TO transkribator;

--
-- Name: referral_payments_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.referral_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.referral_payments_id_seq OWNER TO transkribator;

--
-- Name: referral_payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.referral_payments_id_seq OWNED BY public.referral_payments.id;


--
-- Name: referral_visits; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.referral_visits (
    id integer NOT NULL,
    referral_code character varying NOT NULL,
    visitor_telegram_id bigint,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.referral_visits OWNER TO transkribator;

--
-- Name: referral_visits_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.referral_visits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.referral_visits_id_seq OWNER TO transkribator;

--
-- Name: referral_visits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.referral_visits_id_seq OWNED BY public.referral_visits.id;


--
-- Name: reminders; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.reminders (
    id integer NOT NULL,
    user_id integer NOT NULL,
    note_id integer,
    fire_ts timestamp without time zone NOT NULL,
    payload text,
    sent_at timestamp without time zone
);


ALTER TABLE public.reminders OWNER TO transkribator;

--
-- Name: reminders_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.reminders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reminders_id_seq OWNER TO transkribator;

--
-- Name: reminders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.reminders_id_seq OWNED BY public.reminders.id;


--
-- Name: transactions; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.transactions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    plan_type character varying NOT NULL,
    amount_rub double precision,
    amount_usd double precision,
    amount_stars integer,
    currency character varying,
    provider_payment_charge_id character varying,
    telegram_payment_charge_id character varying,
    external_payment_id character varying,
    payment_method character varying,
    status character varying DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.transactions OWNER TO transkribator;

--
-- Name: transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transactions_id_seq OWNER TO transkribator;

--
-- Name: transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.transactions_id_seq OWNED BY public.transactions.id;


--
-- Name: transcriptions; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.transcriptions (
    id integer NOT NULL,
    user_id integer,
    filename character varying,
    file_size_mb double precision NOT NULL,
    audio_duration_minutes double precision NOT NULL,
    raw_transcript text,
    formatted_transcript text,
    transcript_length integer DEFAULT 0 NOT NULL,
    transcription_service character varying DEFAULT 'deepinfra'::character varying,
    formatting_service character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    processing_time_seconds double precision
);


ALTER TABLE public.transcriptions OWNER TO transkribator;

--
-- Name: transcriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.transcriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transcriptions_id_seq OWNER TO transkribator;

--
-- Name: transcriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.transcriptions_id_seq OWNED BY public.transcriptions.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: transkribator
--

CREATE TABLE public.users (
    id integer NOT NULL,
    telegram_id bigint NOT NULL,
    username character varying,
    first_name character varying,
    last_name character varying,
    current_plan character varying DEFAULT 'free'::character varying,
    plan_expires_at timestamp without time zone,
    total_minutes_transcribed double precision DEFAULT 0 NOT NULL,
    minutes_used_this_month double precision DEFAULT 0 NOT NULL,
    last_reset_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    total_generations integer DEFAULT 0 NOT NULL,
    generations_used_this_month integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true NOT NULL,
    beta_enabled boolean DEFAULT false,
    google_connected boolean DEFAULT false,
    timezone character varying(64)
);


ALTER TABLE public.users OWNER TO transkribator;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: transkribator
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO transkribator;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: transkribator
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: api_keys id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.api_keys ALTER COLUMN id SET DEFAULT nextval('public.api_keys_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.events ALTER COLUMN id SET DEFAULT nextval('public.events_id_seq'::regclass);


--
-- Name: google_credentials id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.google_credentials ALTER COLUMN id SET DEFAULT nextval('public.google_credentials_id_seq'::regclass);


--
-- Name: note_chunks id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_chunks ALTER COLUMN id SET DEFAULT nextval('public.note_chunks_id_seq'::regclass);


--
-- Name: note_groups id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_groups ALTER COLUMN id SET DEFAULT nextval('public.note_groups_id_seq'::regclass);


--
-- Name: note_versions id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_versions ALTER COLUMN id SET DEFAULT nextval('public.note_versions_id_seq'::regclass);


--
-- Name: notes id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.notes ALTER COLUMN id SET DEFAULT nextval('public.notes_id_seq'::regclass);


--
-- Name: plans id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.plans ALTER COLUMN id SET DEFAULT nextval('public.plans_id_seq'::regclass);


--
-- Name: processing_jobs id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.processing_jobs ALTER COLUMN id SET DEFAULT nextval('public.processing_jobs_id_seq'::regclass);


--
-- Name: promo_activations id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.promo_activations ALTER COLUMN id SET DEFAULT nextval('public.promo_activations_id_seq'::regclass);


--
-- Name: promo_codes id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.promo_codes ALTER COLUMN id SET DEFAULT nextval('public.promo_codes_id_seq'::regclass);


--
-- Name: referral_attribution id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_attribution ALTER COLUMN id SET DEFAULT nextval('public.referral_attribution_id_seq'::regclass);


--
-- Name: referral_links id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_links ALTER COLUMN id SET DEFAULT nextval('public.referral_links_id_seq'::regclass);


--
-- Name: referral_payments id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_payments ALTER COLUMN id SET DEFAULT nextval('public.referral_payments_id_seq'::regclass);


--
-- Name: referral_visits id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_visits ALTER COLUMN id SET DEFAULT nextval('public.referral_visits_id_seq'::regclass);


--
-- Name: reminders id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.reminders ALTER COLUMN id SET DEFAULT nextval('public.reminders_id_seq'::regclass);


--
-- Name: transactions id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.transactions ALTER COLUMN id SET DEFAULT nextval('public.transactions_id_seq'::regclass);


--
-- Name: transcriptions id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.transcriptions ALTER COLUMN id SET DEFAULT nextval('public.transcriptions_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: google_credentials google_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.google_credentials
    ADD CONSTRAINT google_credentials_pkey PRIMARY KEY (id);


--
-- Name: note_chunks note_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_chunks
    ADD CONSTRAINT note_chunks_pkey PRIMARY KEY (id);


--
-- Name: note_group_links note_group_links_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_group_links
    ADD CONSTRAINT note_group_links_pkey PRIMARY KEY (note_id, group_id);


--
-- Name: note_groups note_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_groups
    ADD CONSTRAINT note_groups_pkey PRIMARY KEY (id);


--
-- Name: note_versions note_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_versions
    ADD CONSTRAINT note_versions_pkey PRIMARY KEY (id);


--
-- Name: notes notes_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.notes
    ADD CONSTRAINT notes_pkey PRIMARY KEY (id);


--
-- Name: plans plans_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (id);


--
-- Name: processing_jobs processing_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_pkey PRIMARY KEY (id);


--
-- Name: promo_activations promo_activations_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.promo_activations
    ADD CONSTRAINT promo_activations_pkey PRIMARY KEY (id);


--
-- Name: promo_codes promo_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_pkey PRIMARY KEY (id);


--
-- Name: referral_attribution referral_attribution_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_attribution
    ADD CONSTRAINT referral_attribution_pkey PRIMARY KEY (id);


--
-- Name: referral_links referral_links_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_links
    ADD CONSTRAINT referral_links_pkey PRIMARY KEY (id);


--
-- Name: referral_payments referral_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_payments
    ADD CONSTRAINT referral_payments_pkey PRIMARY KEY (id);


--
-- Name: referral_visits referral_visits_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_visits
    ADD CONSTRAINT referral_visits_pkey PRIMARY KEY (id);


--
-- Name: reminders reminders_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.reminders
    ADD CONSTRAINT reminders_pkey PRIMARY KEY (id);


--
-- Name: transactions transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_pkey PRIMARY KEY (id);


--
-- Name: transcriptions transcriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.transcriptions
    ADD CONSTRAINT transcriptions_pkey PRIMARY KEY (id);


--
-- Name: api_keys uq_api_keys_key_hash; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash);


--
-- Name: note_group_links uq_note_group_links_note_group; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_group_links
    ADD CONSTRAINT uq_note_group_links_note_group UNIQUE (note_id, group_id);


--
-- Name: plans uq_plans_name; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT uq_plans_name UNIQUE (name);


--
-- Name: promo_codes uq_promo_codes_code; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT uq_promo_codes_code UNIQUE (code);


--
-- Name: referral_attribution uq_referral_attribution_visitor_telegram_id; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_attribution
    ADD CONSTRAINT uq_referral_attribution_visitor_telegram_id UNIQUE (visitor_telegram_id);


--
-- Name: referral_links uq_referral_links_code; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.referral_links
    ADD CONSTRAINT uq_referral_links_code UNIQUE (code);


--
-- Name: users uq_users_telegram_id; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_telegram_id UNIQUE (telegram_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_note_versions_note_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX idx_note_versions_note_id ON public.note_versions USING btree (note_id, version);


--
-- Name: ix_api_keys_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_api_keys_user_id ON public.api_keys USING btree (user_id);


--
-- Name: ix_events_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_events_id ON public.events USING btree (id);


--
-- Name: ix_events_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_events_user_id ON public.events USING btree (user_id);


--
-- Name: ix_google_credentials_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_google_credentials_id ON public.google_credentials USING btree (id);


--
-- Name: ix_google_credentials_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_google_credentials_user_id ON public.google_credentials USING btree (user_id);


--
-- Name: ix_note_chunks_note_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_note_chunks_note_id ON public.note_chunks USING btree (note_id);


--
-- Name: ix_note_chunks_user_chunk; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_note_chunks_user_chunk ON public.note_chunks USING btree (user_id, note_id, chunk_index);


--
-- Name: ix_note_chunks_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_note_chunks_user_id ON public.note_chunks USING btree (user_id);


--
-- Name: ix_note_groups_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_note_groups_user_id ON public.note_groups USING btree (user_id);


--
-- Name: ix_notes_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_notes_id ON public.notes USING btree (id);


--
-- Name: ix_notes_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_notes_user_id ON public.notes USING btree (user_id);


--
-- Name: ix_processing_jobs_created_at; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_processing_jobs_created_at ON public.processing_jobs USING btree (created_at);


--
-- Name: ix_processing_jobs_note_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_processing_jobs_note_id ON public.processing_jobs USING btree (note_id);


--
-- Name: ix_processing_jobs_status; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_processing_jobs_status ON public.processing_jobs USING btree (status);


--
-- Name: ix_processing_jobs_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_processing_jobs_user_id ON public.processing_jobs USING btree (user_id);


--
-- Name: ix_promo_activations_promo_code_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_promo_activations_promo_code_id ON public.promo_activations USING btree (promo_code_id);


--
-- Name: ix_promo_activations_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_promo_activations_user_id ON public.promo_activations USING btree (user_id);


--
-- Name: ix_promo_codes_code; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE UNIQUE INDEX ix_promo_codes_code ON public.promo_codes USING btree (code);


--
-- Name: ix_referral_attribution_referral_code; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_referral_attribution_referral_code ON public.referral_attribution USING btree (referral_code);


--
-- Name: ix_referral_links_user_telegram_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_referral_links_user_telegram_id ON public.referral_links USING btree (user_telegram_id);


--
-- Name: ix_referral_payments_payer_telegram_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_referral_payments_payer_telegram_id ON public.referral_payments USING btree (payer_telegram_id);


--
-- Name: ix_referral_payments_referral_code; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_referral_payments_referral_code ON public.referral_payments USING btree (referral_code);


--
-- Name: ix_referral_visits_referral_code; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_referral_visits_referral_code ON public.referral_visits USING btree (referral_code);


--
-- Name: ix_referral_visits_visitor_telegram_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_referral_visits_visitor_telegram_id ON public.referral_visits USING btree (visitor_telegram_id);


--
-- Name: ix_reminders_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_reminders_id ON public.reminders USING btree (id);


--
-- Name: ix_reminders_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_reminders_user_id ON public.reminders USING btree (user_id);


--
-- Name: ix_transactions_external_payment_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_transactions_external_payment_id ON public.transactions USING btree (external_payment_id);


--
-- Name: ix_transactions_provider_payment_charge_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_transactions_provider_payment_charge_id ON public.transactions USING btree (provider_payment_charge_id);


--
-- Name: ix_transactions_telegram_payment_charge_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_transactions_telegram_payment_charge_id ON public.transactions USING btree (telegram_payment_charge_id);


--
-- Name: ix_transactions_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_transactions_user_id ON public.transactions USING btree (user_id);


--
-- Name: ix_transcriptions_user_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE INDEX ix_transcriptions_user_id ON public.transcriptions USING btree (user_id);


--
-- Name: ix_users_telegram_id; Type: INDEX; Schema: public; Owner: transkribator
--

CREATE UNIQUE INDEX ix_users_telegram_id ON public.users USING btree (telegram_id);


--
-- Name: events events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: api_keys fk_api_keys_users; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT fk_api_keys_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: promo_activations fk_promo_activations_promo_codes; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.promo_activations
    ADD CONSTRAINT fk_promo_activations_promo_codes FOREIGN KEY (promo_code_id) REFERENCES public.promo_codes(id);


--
-- Name: promo_activations fk_promo_activations_users; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.promo_activations
    ADD CONSTRAINT fk_promo_activations_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: transactions fk_transactions_users; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT fk_transactions_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: transcriptions fk_transcriptions_users; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.transcriptions
    ADD CONSTRAINT fk_transcriptions_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: google_credentials google_credentials_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.google_credentials
    ADD CONSTRAINT google_credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: note_chunks note_chunks_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_chunks
    ADD CONSTRAINT note_chunks_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.notes(id);


--
-- Name: note_chunks note_chunks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_chunks
    ADD CONSTRAINT note_chunks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: note_group_links note_group_links_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_group_links
    ADD CONSTRAINT note_group_links_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.note_groups(id) ON DELETE CASCADE;


--
-- Name: note_group_links note_group_links_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_group_links
    ADD CONSTRAINT note_group_links_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.notes(id) ON DELETE CASCADE;


--
-- Name: note_groups note_groups_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_groups
    ADD CONSTRAINT note_groups_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: note_versions note_versions_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.note_versions
    ADD CONSTRAINT note_versions_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.notes(id);


--
-- Name: notes notes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.notes
    ADD CONSTRAINT notes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: processing_jobs processing_jobs_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.notes(id);


--
-- Name: processing_jobs processing_jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.processing_jobs
    ADD CONSTRAINT processing_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: reminders reminders_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.reminders
    ADD CONSTRAINT reminders_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.notes(id);


--
-- Name: reminders reminders_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: transkribator
--

ALTER TABLE ONLY public.reminders
    ADD CONSTRAINT reminders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict Xu1hN2eNWuC8tZVELcbmKlh2DXy9nUu1nl0YEggvuXSkKFQ6iLE6JXHdgMy4bRR

