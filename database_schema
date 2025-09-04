

-- Crée la base de données si elle n'existe pas déjà, pour éviter les erreurs.
CREATE DATABASE IF NOT EXISTS pallet_optimizer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Sélectionne la base de données pour les commandes suivantes.
USE pallet_optimizer;

-- --------------------------------------------------------

--
-- Structure de la table `pallet_configs`
-- Cette table stocke chaque combinaison unique de dimensions pour éviter les doublons.
-- Chaque ligne représente un "problème" de palettisation unique.
--

CREATE TABLE IF NOT EXISTS `pallet_configs` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `pallet_L` INT NOT NULL COMMENT 'Longueur de la palette en mm',
  `pallet_W` INT NOT NULL COMMENT 'Largeur de la palette en mm',
  `box_l` INT NOT NULL COMMENT 'Longueur du carton en mm',
  `box_w` INT NOT NULL COMMENT 'Largeur du carton en mm',
  -- Crée une contrainte pour s'assurer qu'on ne peut pas insérer deux fois la même combinaison de dimensions.
  UNIQUE KEY `unique_dims` (`pallet_L`, `pallet_W`, `box_l`, `box_w`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- --------------------------------------------------------

--
-- Structure de la table `generated_templates`
-- Cette table stocke tous les plans de palettisation (templates) générés pour une configuration donnée.
--

CREATE TABLE IF NOT EXISTS `generated_templates` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `config_id` INT NOT NULL COMMENT 'Clé étrangère liant à la table pallet_configs',
  `template_data` JSON NOT NULL COMMENT 'Toutes les données du template (couches, cartons, score, etc.) au format JSON',
  `score` FLOAT NOT NULL COMMENT 'Score de stabilité et d''efficacité calculé par le moteur',
  `is_in_production` BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Drapeau (TRUE/FALSE) pour marquer le template utilisé par défaut',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Date et heure de la création du template',

  -- Crée le lien entre cette table et la table `pallet_configs`.
  -- Assure l'intégrité des données : on ne peut pas avoir un template sans configuration associée.
  FOREIGN KEY (`config_id`) REFERENCES `pallet_configs`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
