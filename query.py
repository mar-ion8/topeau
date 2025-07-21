q_1 = ''' CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
                            srs_name TEXT NOT NULL,
                            srs_id INTEGER NOT NULL PRIMARY KEY,
                            organization TEXT NOT NULL,
                            organization_coordsys_id INTEGER NOT NULL,
                            definition TEXT NOT NULL,
                            description TEXT 
                            ) '''

q_2 = ''' INSERT OR REPLACE INTO gpkg_spatial_ref_sys 
                        (srs_name, srs_id, organization, organization_coordsys_id, definition, description)
                        VALUES (?, ?, ?, ?, ?, ?) '''

params_q2 = ('RGF93 / Lambert-93',
                2154,
                'EPSG',
                2154,
                'PROJCS["RGF93 / Lambert-93",GEOGCS["RGF93",DATUM["Reseau_Geodesique_Francais_1993",SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],AUTHORITY["EPSG","6171"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4171"]],PROJECTION["Lambert_Conformal_Conic_2SP"],PARAMETER["standard_parallel_1",49],PARAMETER["standard_parallel_2",44],PARAMETER["latitude_of_origin",46.5],PARAMETER["central_meridian",3],PARAMETER["false_easting",700000],PARAMETER["false_northing",6600000],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AUTHORITY["EPSG","2154"]]',
                'Lambert 93 France'
            )

q_3 = '''CREATE TABLE IF NOT EXISTS gpkg_contents (
                            table_name TEXT NOT NULL PRIMARY KEY,
                            data_type TEXT NOT NULL,
                            identifier TEXT UNIQUE,
                            description TEXT DEFAULT '',
                            last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                            min_x DOUBLE,
                            min_y DOUBLE,
                            max_x DOUBLE,
                            max_y DOUBLE,
                            srs_id INTEGER,
                            CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
                        ) '''

q_4 = ''' CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
                            table_name TEXT NOT NULL,
                            column_name TEXT NOT NULL,
                            geometry_type_name TEXT NOT NULL,
                            srs_id INTEGER NOT NULL,
                            z TINYINT NOT NULL,
                            m TINYINT NOT NULL,
                            CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
                            CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
                            CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
                        )'''

q_5 = ''' CREATE TABLE IF NOT EXISTS gpkg_extensions (
                    table_name TEXT,
                    column_name TEXT,
                    extension_name TEXT NOT NULL,
                    definition TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name)
                ) '''

q_6 = ''' CREATE TABLE IF NOT EXISTS gpkg_data_columns (
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    name TEXT,
                    title TEXT,
                    description TEXT,
                    mime_type TEXT,
                    constraint_name TEXT,
                    CONSTRAINT pk_gdc PRIMARY KEY (table_name, column_name)
                )'''

q_7 = ''' INSERT INTO gpkg_contents 
                        (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''

q_8 = ''' INSERT INTO gpkg_geometry_columns 
                        (table_name, column_name, geometry_type_name, srs_id, z, m) 
                        VALUES (?, ?, ?, ?, ?, ?)'''

q_9 = ''' CREATE TABLE hauteur_eau (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    geom GEOMETRY,
                    niveau_eau REAL,
                    nom TEXT,
                    surface_eau_m2 REAL,
                    volume_eau_m3 REAL,
                    classe_1 REAL,
                    classe_2 REAL,
                    classe_3 REAL,
                    classe_4 REAL,
                    classe_5 REAL,
                    classe_6 REAL,
                    classe_7 REAL,
                    nom_fichier TEXT
                )'''

q_10 = ''' INSERT INTO gpkg_contents 
                        (table_name, data_type, identifier, description, last_change, srs_id) 
                        VALUES (?, ?, ?, ?, ?, ?) '''

q_11 = ''' INSERT INTO gpkg_geometry_columns 
                        (table_name, column_name, geometry_type_name, srs_id, z, m) 
                        VALUES (?, ?, ?, ?, ?, ?) '''

q_12 = '''CREATE TABLE mesure (
                    id INTEGER PRIMARY KEY, 
                    date DATE,
                    niveau_eau REAL
                ) '''

q_13 = ''' CREATE TABLE metadata_md1 (
                    id INTEGER PRIMARY KEY, 
                    nom_du_fichier TEXT,            
                    mots_clefs TEXT,
                    createur TEXT,
                    contributeur TEXT,
                    referent_metadonnees TEXT,
                    personnes_a_contacter TEXT,
                    description TEXT,
                    date_de_creation DATE,
                    type_de_donnees TEXT,
                    format TEXT,
                    langage TEXT,
                    relation TEXT,
                    extension_spatiale TEXT, 
                    provenance TEXT,
                    droits TEXT           
                    )'''

q_14 = ''' INSERT INTO metadata_md1(
                    nom_du_fichier,
                    mots_clefs,
                    createur,
                    contributeur,
                    referent_metadonnees,
                    personnes_a_contacter,
                    description,
                    date_de_creation,
                    type_de_donnees,
                    format,
                    langage,
                    relation,
                    extension_spatiale,
                    provenance,
                    droits
                ) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? )'''

q_15 = ''' CREATE TABLE metadata_md2 (
                    id INTEGER PRIMARY KEY, 
                    date___mesure TEXT,            
                    niveau_eau___mesure TEXT,
                    nom___zone_etude TEXT,
                    surface_m2___zone_etude TEXT,
                    min_parcelle___zone_etude TEXT,
                    max_parcelle___zone_etude TEXT,
                    moyenne_parcelle___zone_etude TEXT,
                    mediane_parcelle___zone_etude TEXT,
                    decile_10___zone_etude TEXT,
                    decile_20___zone_etude TEXT,
                    decile_30___zone_etude TEXT,
                    decile_40___zone_etude TEXT,
                    decile_50___zone_etude TEXT,
                    decile_60___zone_etude TEXT,
                    decile_70___zone_etude TEXT,
                    decile_80___zone_etude TEXT,
                    decile_90___zone_etude TEXT,
                    niveau_eau___hauteur_eau TEXT,
                    nom___hauteur_eau TEXT,
                    surface_eau_m2___hauteur_eau TEXT,
                    volume_eau_m3___hauteur_eau TEXT,
                    classe_1___hauteur_eau TEXT,
                    classe_2___hauteur_eau TEXT, 
                    classe_3___hauteur_eau TEXT, 
                    classe_4___hauteur_eau TEXT,
                    classe_5___hauteur_eau TEXT,
                    classe_6___hauteur_eau TEXT, 
                    classe_7___hauteur_eau TEXT,
                    nom_fichier___hauteur_eau TEXT         
                ) '''

q_16 = ''' INSERT INTO metadata_md2(
                    date___mesure,            
                    niveau_eau___mesure,
                    nom___zone_etude,
                    surface_m2___zone_etude,
                    min_parcelle___zone_etude,
                    max_parcelle___zone_etude,
                    moyenne_parcelle___zone_etude,
                    mediane_parcelle___zone_etude,
                    decile_10___zone_etude,
                    decile_20___zone_etude,
                    decile_30___zone_etude,
                    decile_40___zone_etude,
                    decile_50___zone_etude,
                    decile_60___zone_etude,
                    decile_70___zone_etude,
                    decile_80___zone_etude,
                    decile_90___zone_etude,
                    niveau_eau___hauteur_eau,
                    nom___hauteur_eau,
                    surface_eau_m2___hauteur_eau,
                    volume_eau_m3___hauteur_eau,
                    classe_1___hauteur_eau,
                    classe_2___hauteur_eau, 
                    classe_3___hauteur_eau, 
                    classe_4___hauteur_eau,
                    classe_5___hauteur_eau,
                    classe_6___hauteur_eau, 
                    classe_7___hauteur_eau,
                    nom_fichier___hauteur_eau
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''

params_q16 = ('Date relevée pour la mesure du niveau d\'eau dans la parcelle (bouée, piézomètre, relevé terrain)',
                    'Niveau relevé pour la mesure du niveau d\'eau dans la parcelle (bouée, piézomètre, relevé terrain)',
                    'Nom donné par l\'utilisateur pour la zone qu\'il étudie',
                    'Surface du polygone correspondant à la zone d\'étude (en m²)',
                    'Point le plus bas de la parcelle (en mètre)',
                    'Point le plus haut de la parcelle (en mètre)',
                    'Elévation moyenne dans la parcelle (en mètre)',
                    'Valeur médiane pour l\'élévation de la parcelle (en mètre)',
                    'Valeur correspondante au premier décile lié à l\'altimétrie de la zone d\'étude (m), aussi considéré comme le point bas de la zone' ,
                    'Valeur correspondante au deuxième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur correspondante au troisième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur correspondante au quatrième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur correspondante au cinquième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur correspondante au sixième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur correspondante au septième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur correspondante au huitième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur correspondante au neuvième décile lié à l\'altimétrie de la zone d\'étude (m)',
                    'Valeur simulée & étudiée pour l\'emprise hydrique dans la parcelle (en mètre)',
                    'Nom donné par l\'utilisateur pour la zone qu\'il étudie',
                    'Surface couverte par l\'eau selon le niveau simulé dans la parcelle (en m²)',
                    'Volume d\'eau dans la zone d\'étude selon le niveau simulé dans la parcelle (en m³)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 1 : 0 - 5 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 2 : 5 - 10 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 3 : 10 - 15 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 4 : 15 - 20 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 5 : 20 - 25 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 6 : 25 - 30 cm (en m²)',
                    'Surface couverte par un niveau d\'eau compris dans la classe 7 : > 30 cm (en m²)',
                    'Nom donné au raster lors de sa génération et son extension')

q_17 = ''' INSERT INTO hauteur_eau 
                           (geom, niveau_eau, nom, surface_eau_m2, volume_eau_m3,
                           classe_1, classe_2, classe_3, classe_4, classe_5, classe_6, classe_7, nom_fichier) 
                           VALUES (ST_GeomFromWKB(?, ?), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) '''

q_18 = ''' INSERT INTO hauteur_eau 
                           (geom,niveau_eau, nom, surface_eau_m2, volume_eau_m3,
                           classe_1, classe_2, classe_3, classe_4, classe_5, classe_6, classe_7, nom_fichier) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''

q_19 = '''  SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) 
            FROM (SELECT ? as min_x, ? as min_y, ? as max_x, ? as max_y
                  UNION 
                  SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name = 'hauteur_eau')'''

q_20 = ''' INSERT INTO hauteur_eau 
                              (niveau_eau, nom, surface_eau_m2, volume_eau_m3,
                              classe_1, classe_2, classe_3, classe_4, classe_5, classe_6, classe_7,
                              nom_fichier) 
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) '''

