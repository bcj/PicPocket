--
-- PostgreSQL database dump
--

-- Dumped from database version 15.4 (Homebrew)
-- Dumped by pg_dump version 15.7 (Homebrew)

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

ALTER TABLE ONLY public.tasks DROP CONSTRAINT tasks_source_fkey;
ALTER TABLE ONLY public.tasks DROP CONSTRAINT tasks_destination_fkey;
ALTER TABLE ONLY public.task_invocations DROP CONSTRAINT task_invocations_task_fkey;
ALTER TABLE ONLY public.images DROP CONSTRAINT images_location_fkey;
ALTER TABLE ONLY public.image_tags DROP CONSTRAINT image_tags_tag_fkey;
ALTER TABLE ONLY public.image_tags DROP CONSTRAINT image_tags_image_fkey;
ALTER TABLE ONLY public.version DROP CONSTRAINT version_pkey;
ALTER TABLE ONLY public.tasks DROP CONSTRAINT tasks_pkey;
ALTER TABLE ONLY public.task_invocations DROP CONSTRAINT task_invocations_pkey;
ALTER TABLE ONLY public.tags DROP CONSTRAINT tags_pkey;
ALTER TABLE ONLY public.tags DROP CONSTRAINT tags_name_key;
ALTER TABLE ONLY public.tags DROP CONSTRAINT tags_escaped_name_key;
ALTER TABLE ONLY public.session_info DROP CONSTRAINT session_info_pkey;
ALTER TABLE ONLY public.relation DROP CONSTRAINT relation_pkey;
ALTER TABLE ONLY public.photo_tags DROP CONSTRAINT photo_tags_pkey;
ALTER TABLE ONLY public.locations DROP CONSTRAINT locations_pkey;
ALTER TABLE ONLY public.locations DROP CONSTRAINT locations_name_key;
ALTER TABLE ONLY public.images DROP CONSTRAINT images_pkey;
ALTER TABLE ONLY public.images DROP CONSTRAINT images_location_path_key;
ALTER TABLE ONLY public.image_tags DROP CONSTRAINT image_tags_pkey;
DROP TABLE public.version;
DROP TABLE public.tasks;
DROP TABLE public.task_invocations;
DROP TABLE public.tags;
DROP TABLE public.session_info;
DROP TABLE public.relation;
DROP TABLE public.photo_tags;
DROP TABLE public.locations;
DROP TABLE public.images;
DROP TABLE public.image_tags;
DROP TYPE public.version_number;
--
-- Name: version_number; Type: TYPE; Schema: public; Owner: testpicpocket
--

CREATE TYPE public.version_number AS (
	major integer,
	minor integer,
	patch integer,
	label text
);


ALTER TYPE public.version_number OWNER TO testpicpocket;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: image_tags; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.image_tags (
    image integer NOT NULL,
    tag integer NOT NULL
);


ALTER TABLE public.image_tags OWNER TO testpicpocket;

--
-- Name: images; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.images (
    id integer NOT NULL,
    hash character(64) NOT NULL,
    creation_date timestamp with time zone NOT NULL,
    last_modified timestamp with time zone NOT NULL,
    name text NOT NULL,
    extension text NOT NULL,
    width integer,
    height integer,
    creator text,
    location integer NOT NULL,
    path text NOT NULL,
    title text,
    caption text,
    alt text,
    rating integer,
    exif json NOT NULL
);


ALTER TABLE public.images OWNER TO testpicpocket;

--
-- Name: images_id_seq; Type: SEQUENCE; Schema: public; Owner: testpicpocket
--

ALTER TABLE public.images ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.images_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: locations; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.locations (
    id integer NOT NULL,
    name text NOT NULL,
    description text,
    path text,
    source boolean DEFAULT false,
    destination boolean DEFAULT false,
    removable boolean DEFAULT false
);


ALTER TABLE public.locations OWNER TO testpicpocket;

--
-- Name: locations_id_seq; Type: SEQUENCE; Schema: public; Owner: testpicpocket
--

ALTER TABLE public.locations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.locations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: photo_tags; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.photo_tags (
    image integer NOT NULL,
    tag integer NOT NULL
);


ALTER TABLE public.photo_tags OWNER TO testpicpocket;

--
-- Name: relation; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.relation (
    image integer NOT NULL,
    parent integer NOT NULL,
    description text
);


ALTER TABLE public.relation OWNER TO testpicpocket;

--
-- Name: session_info; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.session_info (
    id integer NOT NULL,
    expires timestamp with time zone NOT NULL,
    data json NOT NULL
);


ALTER TABLE public.session_info OWNER TO testpicpocket;

--
-- Name: session_info_id_seq; Type: SEQUENCE; Schema: public; Owner: testpicpocket
--

ALTER TABLE public.session_info ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.session_info_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: tags; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.tags (
    id integer NOT NULL,
    name text NOT NULL,
    escaped_name text,
    depth integer NOT NULL,
    description text
);


ALTER TABLE public.tags OWNER TO testpicpocket;

--
-- Name: tags_id_seq; Type: SEQUENCE; Schema: public; Owner: testpicpocket
--

ALTER TABLE public.tags ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.tags_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: task_invocations; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.task_invocations (
    task text NOT NULL,
    last_ran timestamp with time zone
);


ALTER TABLE public.task_invocations OWNER TO testpicpocket;

--
-- Name: tasks; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.tasks (
    name text NOT NULL,
    description text,
    source integer NOT NULL,
    destination integer NOT NULL,
    configuration json NOT NULL
);


ALTER TABLE public.tasks OWNER TO testpicpocket;

--
-- Name: version; Type: TABLE; Schema: public; Owner: testpicpocket
--

CREATE TABLE public.version (
    id integer NOT NULL,
    version public.version_number NOT NULL
);


ALTER TABLE public.version OWNER TO testpicpocket;

--
-- Name: version_id_seq; Type: SEQUENCE; Schema: public; Owner: testpicpocket
--

ALTER TABLE public.version ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.version_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Data for Name: image_tags; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.image_tags (image, tag) FROM stdin;
1	4
1	5
2	4
2	5
\.


--
-- Data for Name: images; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.images (id, hash, creation_date, last_modified, name, extension, width, height, creator, location, path, title, caption, alt, rating, exif) FROM stdin;
1	1db98fadd6f7eee109b45d2be1deb7d05f9ec371e9657219f851744fa0c59751	2023-05-20 14:54:04-05	2023-05-20 14:54:04-05	b	jpg	5	5	bcj	1	b.jpg	\N	\N	\N	\N	{}
2	bd6a7d871db084654f2aeb1de396499961502946fa914a3293950943ee1ada60	2023-05-20 14:53:04-05	2023-05-20 14:53:04-05	a	jpg	5	5	bcj	1	a.jpg	Title	a description	alt text	5	{}
3	bd6a7d871db084654f2aeb1de396499961502946fa914a3293950943ee1ada60	2023-05-20 14:53:04-05	2023-05-20 14:53:04-05	a	jpg	5	5	\N	2	a.jpg	\N	\N	\N	\N	{}
4	1db98fadd6f7eee109b45d2be1deb7d05f9ec371e9657219f851744fa0c59751	2023-05-20 14:54:04-05	2023-05-20 14:54:04-05	b	jpg	5	5	\N	2	subdirectory/b.jpg	\N	\N	\N	\N	{}
\.


--
-- Data for Name: locations; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.locations (id, name, description, path, source, destination, removable) FROM stdin;
1	main	main storage	/private/var/folders/42/y27827s955l88y_kdqfg8x240000gn/T/pytest-of-bcj/pytest-228/test_create_backup0/main	t	t	f
2	portable	\N	\N	f	t	t
\.


--
-- Data for Name: photo_tags; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.photo_tags (image, tag) FROM stdin;
\.


--
-- Data for Name: relation; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.relation (image, parent, description) FROM stdin;
\.


--
-- Data for Name: session_info; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.session_info (id, expires, data) FROM stdin;
\.


--
-- Data for Name: tags; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.tags (id, name, escaped_name, depth, description) FROM stdin;
1	//dogs/	//dogs/	1	dogs are cool
2	//tag/	//tag/	1	a tag
3	//tag/that/is/nested/	//tag/that/is/nested/	4	another tag
4	//tag/that/	//tag/that/	2	\N
5	//other/	//other/	1	\N
\.


--
-- Data for Name: task_invocations; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.task_invocations (task, last_ran) FROM stdin;
\.


--
-- Data for Name: tasks; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.tasks (name, description, source, destination, configuration) FROM stdin;
my task	a task description	2	1	{"tags": ["a", "b/c"], "source": "subdirectory/{year}/{month}", "destination": "from_portable/{file}"}
reversed	\N	1	2	{"source": "directory", "destination": "from_main/{file}"}
portable task	a task that only touches portable	2	2	{"creator": "bcj", "formats": [".bmp"]}
\.


--
-- Data for Name: version; Type: TABLE DATA; Schema: public; Owner: testpicpocket
--

COPY public.version (id, version) FROM stdin;
1	(0,1,0,)
\.


--
-- Name: images_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testpicpocket
--

SELECT pg_catalog.setval('public.images_id_seq', 4, true);


--
-- Name: locations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testpicpocket
--

SELECT pg_catalog.setval('public.locations_id_seq', 2, true);


--
-- Name: session_info_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testpicpocket
--

SELECT pg_catalog.setval('public.session_info_id_seq', 1, false);


--
-- Name: tags_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testpicpocket
--

SELECT pg_catalog.setval('public.tags_id_seq', 5, true);


--
-- Name: version_id_seq; Type: SEQUENCE SET; Schema: public; Owner: testpicpocket
--

SELECT pg_catalog.setval('public.version_id_seq', 1, true);


--
-- Name: image_tags image_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.image_tags
    ADD CONSTRAINT image_tags_pkey PRIMARY KEY (image, tag);


--
-- Name: images images_location_path_key; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_location_path_key UNIQUE (location, path);


--
-- Name: images images_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_pkey PRIMARY KEY (id);


--
-- Name: locations locations_name_key; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT locations_name_key UNIQUE (name);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (id);


--
-- Name: photo_tags photo_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.photo_tags
    ADD CONSTRAINT photo_tags_pkey PRIMARY KEY (image, tag);


--
-- Name: relation relation_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.relation
    ADD CONSTRAINT relation_pkey PRIMARY KEY (image, parent);


--
-- Name: session_info session_info_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.session_info
    ADD CONSTRAINT session_info_pkey PRIMARY KEY (id);


--
-- Name: tags tags_escaped_name_key; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_escaped_name_key UNIQUE (escaped_name);


--
-- Name: tags tags_name_key; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_name_key UNIQUE (name);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (id);


--
-- Name: task_invocations task_invocations_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.task_invocations
    ADD CONSTRAINT task_invocations_pkey PRIMARY KEY (task);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (name);


--
-- Name: version version_pkey; Type: CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.version
    ADD CONSTRAINT version_pkey PRIMARY KEY (id);


--
-- Name: image_tags image_tags_image_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.image_tags
    ADD CONSTRAINT image_tags_image_fkey FOREIGN KEY (image) REFERENCES public.images(id) ON DELETE CASCADE;


--
-- Name: image_tags image_tags_tag_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.image_tags
    ADD CONSTRAINT image_tags_tag_fkey FOREIGN KEY (tag) REFERENCES public.tags(id) ON DELETE CASCADE;


--
-- Name: images images_location_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_location_fkey FOREIGN KEY (location) REFERENCES public.locations(id) ON DELETE CASCADE;


--
-- Name: task_invocations task_invocations_task_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.task_invocations
    ADD CONSTRAINT task_invocations_task_fkey FOREIGN KEY (task) REFERENCES public.tasks(name) ON DELETE CASCADE;


--
-- Name: tasks tasks_destination_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_destination_fkey FOREIGN KEY (destination) REFERENCES public.locations(id) ON DELETE CASCADE;


--
-- Name: tasks tasks_source_fkey; Type: FK CONSTRAINT; Schema: public; Owner: testpicpocket
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_source_fkey FOREIGN KEY (source) REFERENCES public.locations(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

