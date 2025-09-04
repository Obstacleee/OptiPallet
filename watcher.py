# Fichier: watcher.py

import json
import time
import pymysql
import pallet_engine
import db_fallback
from sender import ModbusSender


class Watcher:
    """
    Classe principale du daemon qui surveille l'automate, interagit avec la BDD
    et orchestre la génération de templates de palettisation.
    """

    def __init__(self, config):
        self.config = config
        self.sender = ModbusSender(config)
        self.db_conn = None
        self.db_cursor = None
        self.db_online = False

        # Variables d'état pour suivre le contexte
        self.last_status = 0
        self.current_dims = None
        self.current_templates = []
        self.last_sent_template_index = -1
        self.last_production_template_id = -1

    def _connect_db(self):
        """Tente de se connecter à la BDD. Gère l'état de la connexion."""
        try:
            # Si la connexion existe déjà, un ping suffit pour vérifier si elle est active
            if self.db_conn and self.db_conn.ping(reconnect=True):
                self.db_online = True
                return

            self.db_conn = pymysql.connect(
                host=self.config['database']['host'],
                user=self.config['database']['user'],
                password=self.config['database']['password'],
                database=self.config['database']['db'],
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5
            )
            self.db_cursor = self.db_conn.cursor()
            self.db_online = True
            print("✅ Connexion à la base de données réussie.")
        except Exception as e:
            if self.db_online:  # Si la connexion vient d'être perdue
                print(f"⚠️ ERREUR de connexion BDD : {e}. Passage en mode fallback JSON.")
            self.db_online = False
            self.db_conn = None

    def _get_config_id(self, dims, create_if_not_exists=False):
        """Trouve l'ID d'une configuration de dimensions, ou la crée si besoin."""
        if not self.db_online: return None
        try:
            p, b = dims['pallet_dims'], dims['box_dims']
            self.db_cursor.execute(
                "SELECT id FROM pallet_configs WHERE pallet_L=%s AND pallet_W=%s AND box_l=%s AND box_w=%s",
                (p['L'], p['W'], b['l'], b['w'])
            )
            result = self.db_cursor.fetchone()
            if result:
                return result['id']
            elif create_if_not_exists:
                self.db_cursor.execute(
                    "INSERT INTO pallet_configs (pallet_L, pallet_W, box_l, box_w) VALUES (%s, %s, %s, %s)",
                    (p['L'], p['W'], b['l'], b['w'])
                )
                self.db_conn.commit()
                return self.db_cursor.lastrowid
            return None
        except Exception as e:
            print(f"Erreur BDD (_get_config_id): {e}")
            self._connect_db()  # Tente de se reconnecter
            return None

    def _load_or_generate_templates(self, dims):
        """Charge les templates depuis la BDD ou le fallback, ou les génère si inexistants."""
        self._connect_db()

        # 1. Essayer de charger depuis la BDD
        if self.db_online:
            config_id = self._get_config_id(dims)
            if config_id:
                self.db_cursor.execute(
                    "SELECT *, template_data as template_json FROM generated_templates WHERE config_id = %s ORDER BY score DESC",
                    (config_id,))
                templates_db = self.db_cursor.fetchall()
                if templates_db:
                    print(f"Trouvé {len(templates_db)} templates dans la BDD.")
                    for tpl in templates_db:
                        tpl['template_data'] = json.loads(tpl['template_json'])
                    return templates_db

        # 2. Si échec BDD, essayer de charger depuis le fallback JSON
        templates_fallback = db_fallback.load_templates(dims)
        if templates_fallback and "templates" in templates_fallback:
            return templates_fallback["templates"]

        # 3. Si tout échoue, générer de nouvelles solutions
        print("Aucun template trouvé en BDD ou en fallback. Lancement du moteur de calcul...")
        results = pallet_engine.generate_pallet_solutions(
            pallet_dims=dims['pallet_dims'], box_dims=dims['box_dims'],
            num_solutions=self.config['engine']['num_solutions_to_find'],
            workers=self.config['engine']['workers']
        )

        if "templates" in results and results["templates"]:
            if self.db_online:
                config_id = self._get_config_id(dims, create_if_not_exists=True)
                for tpl in results['templates']:
                    self.db_cursor.execute(
                        "INSERT INTO generated_templates (config_id, template_data, score) VALUES (%s, %s, %s)",
                        (config_id, json.dumps(tpl), tpl['score'])
                    )
                self.db_conn.commit()
                print("Nouveaux templates sauvegardés en BDD.")

            db_fallback.save_templates(dims, results)
            return results['templates']

        return []

    def handle_display_request(self):
        """Gère la commande 'afficher un modèle' (statut=1)."""
        dims = self.sender.read_dimensions()
        if not dims:
            print("  ❌ Impossible de lire les dimensions depuis l'automate.")
            return

        self.current_dims = dims
        self.current_templates = self._load_or_generate_templates(dims)

        if not self.current_templates:
            print("  ❌ Aucun template disponible pour ces dimensions.")
            self.sender.write_32bit_int(self.config['modbus_addresses']['template_count'], 0)
            return

        self.sender.write_32bit_int(self.config['modbus_addresses']['template_count'], len(self.current_templates))

        req_index = self.sender.read_32bit_int(self.config['modbus_addresses']['template_request'])
        req_index = req_index - 1 if req_index is not None and req_index > 0 else 0

        if not (0 <= req_index < len(self.current_templates)):
            print(f"  Index demandé ({req_index + 1}) invalide. Affichage du premier.")
            req_index = 0

        self.last_sent_template_index = req_index
        template_to_send = self.current_templates[req_index]
        # La structure peut être {id:..., template_data:{...}} ou juste {...}
        data_to_send = template_to_send.get('template_data', template_to_send)
        self.sender.send_template(data_to_send)

    def handle_set_production_request(self):
        """Gère la commande 'mettre en production' (statut=2)."""
        if self.last_sent_template_index == -1 or not self.current_dims:
            print("  ❌ Commande invalide: aucun template n'a été affiché récemment.")
            return

        self._connect_db()
        if not self.db_online:
            print("  ❌ Impossible de mettre en production: connexion BDD requise.")
            return

        config_id = self._get_config_id(self.current_dims)
        if not config_id: return

        self.db_cursor.execute("SELECT id FROM generated_templates WHERE config_id = %s AND is_in_production = TRUE",
                               (config_id,))
        current_prod = self.db_cursor.fetchone()
        if current_prod:
            self.last_production_template_id = current_prod['id']

        self.db_cursor.execute("UPDATE generated_templates SET is_in_production = FALSE WHERE config_id = %s",
                               (config_id,))

        # L'ID du template est dans l'objet que nous avons chargé depuis la BDD
        template_id_to_set = self.current_templates[self.last_sent_template_index]['id']
        self.db_cursor.execute("UPDATE generated_templates SET is_in_production = TRUE WHERE id = %s",
                               (template_id_to_set,))
        self.db_conn.commit()
        print(f"  ✅ Template ID {template_id_to_set} mis en production.")

    def handle_revert_request(self):
        """Gère la commande 'retour arrière' (statut=3)."""
        if self.last_production_template_id == -1:
            print("  ❌ Commande invalide: aucun modèle de production précédent n'est mémorisé.")
            return

        self._connect_db()
        if not self.db_online:
            print("  ❌ Impossible de faire un retour arrière: connexion BDD requise.")
            return

        config_id = self._get_config_id(self.current_dims)
        if not config_id: return

        self.db_cursor.execute("UPDATE generated_templates SET is_in_production = FALSE WHERE config_id = %s",
                               (config_id,))
        self.db_cursor.execute("UPDATE generated_templates SET is_in_production = TRUE WHERE id = %s",
                               (self.last_production_template_id,))
        self.db_conn.commit()

        self.db_cursor.execute("SELECT template_data FROM generated_templates WHERE id = %s",
                               (self.last_production_template_id,))
        template_to_send_db = self.db_cursor.fetchone()
        if template_to_send_db:
            template_to_send = json.loads(template_to_send_db['template_data'])
            self.sender.send_template(template_to_send)
            print(f"  ✅ Retour au modèle de production précédent (ID: {self.last_production_template_id}).")
            self.last_production_template_id = -1

    def run(self):
        """Boucle principale du watcher, conçue pour tourner 24/7."""
        print("--- 🚀 WATCHER DÉMARRÉ ---")
        while True:
            try:
                if not self.sender.is_connected():
                    print("PLC non connecté. Tentative...")
                    if self.sender.connect():
                        print("✅ Reconnexion PLC réussie.")
                        self.sender.write_32bit_int(self.config['modbus_addresses']['error_status'], 0)
                    else:
                        time.sleep(5)
                        continue

                status = self.sender.read_32bit_int(self.config['modbus_addresses']['status'])

                if status is None:
                    print("Perte de communication avec l'automate...")
                    self.sender.disconnect()
                    continue

                if status != self.last_status and status != 0:
                    print(f"🔥 Ordre reçu : {status}")
                    self.last_status = status
                    self.sender.write_32bit_int(self.config['modbus_addresses']['status'], 9)

                    if status == 1:
                        self.handle_display_request()
                    elif status == 2:
                        self.handle_set_production_request()
                    elif status == 3:
                        self.handle_revert_request()

                    print("  Tâche terminée. Retour au statut d'attente.")
                    self.sender.write_32bit_int(self.config['modbus_addresses']['status'], 0)
                    self.last_status = 0

                elif status == 0:
                    self.last_status = 0

            except Exception as e:
                print(f"❌ ERREUR CRITIQUE DANS LA BOUCLE : {e}. Tentative de poursuite...")
                try:
                    if not self.sender.is_connected(): self.sender.connect()
                    self.sender.write_32bit_int(self.config['modbus_addresses']['error_status'], 1)
                except Exception as e2:
                    print(f"Impossible de signaler l'erreur à l'automate : {e2}")

            time.sleep(self.config['watcher']['polling_interval_seconds'])


if __name__ == "__main__":
    with open('config.json', 'r') as f:
        config = json.load(f)

    watcher = Watcher(config)
    watcher.run()