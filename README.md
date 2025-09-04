# OptiPallet 📦

![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)

Moteur d'optimisation de palettisation 2D en Python (avec Google OR-Tools) doté d'une interface Modbus TCP pour une intégration directe avec des automates industriels (PLC).

Ce projet fournit une solution complète pour calculer les plans de pose optimaux de cartons sur des palettes, en tenant compte de contraintes de stabilité complexes, et en communiquant les résultats à un automate pour une exécution robotisée.

---
## ✨ Fonctionnalités Clés

* **Optimisation Optimale :** Utilise **Google OR-Tools** pour trouver le nombre maximal de cartons par couche.
* **Stabilité Intelligente :** Génère des couches imbriquées ("croisées") et utilise un **système de score** pour choisir les templates les plus stables.
* **Architecture 24/7 :** Conçu pour tourner en continu grâce à une architecture de "watcher" résiliente qui gère les déconnexions.
* **Communication Industrielle :** Intègre un serveur de commandes via **Modbus TCP** pour un dialogue direct avec un automate.
* **Persistance des Données :** Sauvegarde toutes les solutions générées dans une base de données **MySQL**.
* **Mode Dégradé Robuste :** Utilise un **fallback sur des fichiers JSON** si la connexion à la base de données est perdue, garantissant une disponibilité maximale.
* **Système de Cache :** Les solutions déjà calculées sont mises en cache pour une réponse instantanée lors de demandes futures.

---
## 🏗️ Architecture

Le système est divisé en plusieurs modules indépendants pour une maintenance et une clarté maximales :

* **`config.json`**: Fichier central pour tous les paramètres (IP, BDD, adresses Modbus).
* **`watcher.py`**: Le cœur de l'application. Ce script tourne en continu, écoute les commandes de l'automate et orchestre les autres modules.
* **`sender.py`**: Bibliothèque de communication qui gère tous les échanges Modbus (lecture/écriture).
* **`pallet_engine.py`**: Le moteur de calcul. Il reçoit des dimensions et retourne les meilleures solutions de palettisation.
* **`db_fallback.py`**: Gère la lecture/écriture des plans dans des fichiers JSON en cas de panne de la base de données.
* **`plc_controller.py`**: Un client Modbus interactif pour simuler les commandes de l'automate et tester le `watcher`.

---
## 🚀 Installation

1.  **Clonez le dépôt :**
    ```bash
    git clone [https://github.com/Obstacleee/OptiPallet.git](https://github.com/Obstacleee/OptiPallet.git)
    cd OptiPallet
    ```

2.  **Créez un environnement virtuel et activez-le :**
    ```bash
    python -m venv .env
    # Windows
    .\.env\Scripts\activate
    # Linux / macOS
    source .env/bin/activate
    ```

3.  **Installez les dépendances :**
     Installez-le :
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurez la base de données :**
    * Assurez-vous d'avoir un serveur MySQL accessible.
    * Créez une base de données (ex: `pallet_optimizer`).
    * Exécutez le script SQL fourni dans `database_schema.sql` pour créer les tables.

5.  **Configurez le projet :**
    * Renommez `config.example.json` en `config.json`.
    * Modifiez `config.json` pour y mettre vos informations (IP de l'automate, identifiants de la BDD).

---
## 📖 Utilisation

1.  **Lancez le service principal (le watcher) :**
    ```bash
    python watcher.py
    ```
    Le service est maintenant en écoute. Il attendra les instructions de l'automate sur l'IP configurée.

2.  **Testez avec le contrôleur (simulateur de PLC) :**
    Ouvrez un **second terminal** et lancez le contrôleur :
    ```bash
    python plc_controller.py
    ```
    Utilisez les commandes interactives (`dims`, `send 1`, `stat`, etc.) pour piloter le watcher et vérifier que tout fonctionne comme prévu.

---
## 🤖 Documentation pour l'Automaticien

Une documentation détaillée du protocole Modbus (mappage des registres, séquence de communication, etc.) est disponible dans le fichier `DOC_MODBUS.md`. Ce document contient toutes les informations nécessaires pour l'intégrateur automate.

---
## 📜 Licence

Ce projet est sous licence APACHE 2.0. Voir le fichier `LICENSE` pour plus de détails.
