# Veille scientifique automatisee

Collecte hebdomadaire d'articles scientifiques (IA, vision par ordinateur, traitement du signal audio/video, langue des signes), lecture des PDF, resume detaille par LLM local, rapport HTML envoye par mail.

Les rapports sont rediges en anglais. Seule la commande vocale Home Assistant reste en francais.

## Architecture

```
Raspberry Pi (conteneur veille)          PC RTX 4060
  1. Collecte arXiv + OpenAlex
  2. Filtrage par score + dedup SQLite
  3. Telechargement PDF + extraction  ->  4. Resume detaille (Ollama)
  5. Rapport HTML + Markdown
  6. Envoi SMTP Gmail
```

Le Pi orchestre (il est toujours allume), le PC ne fait que l'inference. Si le PC est
eteint au moment du declenchement, le service attend jusqu'a `ollama.wait_minutes`
avant de basculer sur les resumes officiels.

## Installation

```bash
mkdir -p /home/homeassistant/veille && cd /home/homeassistant/veille
# copier les fichiers du projet ici
cp config.example.yaml config.yaml
cp .env.example .env
nano .env          # SMTP_USER, SMTP_PASSWORD (mot de passe application Gmail), MAIL_TO
nano config.yaml   # ollama.url = IP du PC, http.token, mots cles
docker compose -f docker-compose-veille.yml build
docker compose -f docker-compose-veille.yml up -d
docker logs -f veille-scientifique
```

## Verifications

```bash
# SMTP
docker compose -f docker-compose-veille.yml run --rm veille test-mail
# Ollama joignable depuis le Pi
docker compose -f docker-compose-veille.yml run --rm veille test-ollama
# Execution complete sans envoi de mail
docker compose -f docker-compose-veille.yml run --rm veille run --no-mail --verbose
```

Les rapports sont ecrits dans `./data/reports/`, les PDF dans `./data/pdf/`,
l'etat dans `./data/state.sqlite`.

## Declenchement

- Automatique : `schedule.weekday` (0 = lundi) et `schedule.hour` dans `config.yaml`.
- Manuel : `curl -X POST -H "X-Token: mon_jeton" http://IP_DU_PI:8137/run`
- Etat : `curl -H "X-Token: mon_jeton" http://IP_DU_PI:8137/status`

## Integration Home Assistant

`configuration.yaml` :

```yaml
rest_command:
  lancer_veille:
    url: "http://10.200.0.20:8137/run"
    method: POST
    headers:
      X-Token: !secret veille_token

rest:
  - resource: "http://10.200.0.20:8137/status"
    scan_interval: 600
    headers:
      X-Token: !secret veille_token
    sensor:
      - name: "Veille scientifique"
        value_template: "{{ value_json.last_run.status if value_json.last_run else 'jamais' }}"
        json_attributes_path: "$.last_run.details"
        json_attributes:
          - selected
          - summarized
          - mail_sent

intent_script:
  LancerVeille:
    action:
      - action: rest_command.lancer_veille
    speech:
      text: "Je lance la veille scientifique, le rapport arrivera par mail."
```

`config/custom_sentences/fr/veille.yaml` :

```yaml
language: "fr"
intents:
  LancerVeille:
    data:
      - sentences:
          - "lance la veille scientifique"
          - "lance la veille"
          - "démarre la veille scientifique"
```

Redemarrage complet du conteneur HA necessaire apres ajout des phrases personnalisees.

## Reglages utiles

| Cle | Effet |
| --- | --- |
| `selection.max_papers` | Nombre d'articles lus integralement (cout GPU lineaire) |
| `selection.min_score` | Seuil de pertinence, monter si trop de bruit |
| `scoring.keywords` | Poids par mot cle, c'est le levier principal |
| `extraction.max_chars` | Taille du texte envoye au LLM, a garder sous `num_ctx` |
| `ollama.think` | Mode raisonnement, inutile ici et couteux en temps |
| `ollama.num_ctx` | 8192 tient sur 8 Go de VRAM. Avec `OLLAMA_FLASH_ATTENTION=1` et `OLLAMA_KV_CACHE_TYPE=q8_0`, tester 16384 ou 32768 |

Compter environ 40 a 90 secondes de GPU par article, soit 10 a 25 minutes pour
15 articles.

## Limites connues

- OpenAlex ne fournit un PDF que pour les articles en acces ouvert ; sinon le resume
  se base sur l'abstract.
- arXiv limite le debit : un delai de 3 secondes est applique entre les requetes.
- Le resume reflete le texte extrait, pas les figures ni les tableaux en image.
- Les proceedings CVPR / ICCV / Interspeech apparaissent souvent d'abord sur arXiv ;
  OpenAlex sert de filet pour les publications en journal.
