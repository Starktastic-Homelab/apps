# Retained-volume startup guard

Every retained volume's workload runs one generic marker guard before its app starts:
[`guard.py`](../../infrastructure/base-configs/files/retained-startup/guard.py), served as ConfigMap
`retained-startup-guard` in each namespace that needs it by
[`retained-startup-guard.yaml`](../../infrastructure/base-configs/templates/retained-startup-guard.yaml).

The init container runs `python3 -I -B /retained-startup/guard.py <app> <root> [<kind> [<marker-file>]]` in the
pinned python image, as the app's own user, with the claim mounted read-only at `<root>`. It accepts only when
`<root>/<marker-file>` (default `.homelab-<app>-<kind>`, kind `data` by default) is a regular file of 1 to 128 bytes
holding exactly `homelab/<app>/<kind>/v1` and a newline. Otherwise it prints one refusal line and exits 1, and the
app does not start.

The guard checks no native files, formats, versions, PostgreSQL system identifiers or database contents, and it never
creates, repairs or rewrites data. A refusal is a stop: investigate the retained image and filesystem identity. Never
create, rename or rewrite a marker to get past it. The only explicit marker file is seerr-ru's, which carries its base
app's name.

| Namespace | Workload | Init container | Guard arguments | uid:gid | Marker file | Content (plus a newline) |
| --- | --- | --- | --- | --- | --- | --- |
| databases | Deployment/pgadmin-pgadmin4 | pgadmin-retained-state | pgadmin /var/lib/pgadmin | 5050:5050 | `/var/lib/pgadmin/.homelab-pgadmin-data` | `homelab/pgadmin/data/v1` |
| databases | StatefulSet/postgres-postgresql | verify-retained-data | postgres /bitnami/postgresql | 1001:1001 | `/bitnami/postgresql/.homelab-postgres-data` | `homelab/postgres/data/v1` |
| databases | StatefulSet/redis-master | verify-retained-data | redis /data | 1001:1001 | `/data/.homelab-redis-data` | `homelab/redis/data/v1` |
| home-automation | Deployment/home-assistant | retained-home-assistant-config | home-assistant /retained | 0:0 | `/retained/.homelab-home-assistant-data` | `homelab/home-assistant/data/v1` |
| home-automation | Deployment/home-assistant | retained-matter-server-data | home-assistant-matter /retained | 1000:1000 | `/retained/.homelab-home-assistant-matter-data` | `homelab/home-assistant-matter/data/v1` |
| home-automation | Deployment/mosquitto | retained-data | mosquitto /retained | 1883:1883 | `/retained/.homelab-mosquitto-data` | `homelab/mosquitto/data/v1` |
| home-automation | Deployment/zigbee2mqtt | retained-data | zigbee2mqtt /retained | 0:0 | `/retained/.homelab-zigbee2mqtt-data` | `homelab/zigbee2mqtt/data/v1` |
| media | Deployment/audiobookshelf | retained-state | audiobookshelf /retained | 0:0 | `/retained/.homelab-audiobookshelf-data` | `homelab/audiobookshelf/data/v1` |
| media | Deployment/autobrr | retained-state | autobrr /config config | 1000:1000 | `/config/.homelab-autobrr-config` | `homelab/autobrr/config/v1` |
| media | Deployment/bazarr | retained-state | bazarr /config config | 1000:1000 | `/config/.homelab-bazarr-config` | `homelab/bazarr/config/v1` |
| media | Deployment/calibre-web | retained-state | calibre-web /retained | 1000:1000 | `/retained/.homelab-calibre-web-data` | `homelab/calibre-web/data/v1` |
| media | Deployment/cineplete | retained-state | cineplete /retained | 0:0 | `/retained/.homelab-cineplete-data` | `homelab/cineplete/data/v1` |
| media | Deployment/cleanuparr | retained-state | cleanuparr /retained | 1000:1000 | `/retained/.homelab-cleanuparr-data` | `homelab/cleanuparr/data/v1` |
| media | Deployment/immich-postgres | verify-retained-data | immich-postgres /data | 999:999 | `/data/.homelab-immich-postgres-data` | `homelab/immich-postgres/data/v1` |
| media | Deployment/lidarr | retained-state | lidarr /retained | 1000:1000 | `/retained/.homelab-lidarr-data` | `homelab/lidarr/data/v1` |
| media | Deployment/lingarr | retained-data | lingarr /retained | 0:0 | `/retained/.homelab-lingarr-data` | `homelab/lingarr/data/v1` |
| media | Deployment/navidrome | retained-state | navidrome /retained | 0:0 | `/retained/.homelab-navidrome-data` | `homelab/navidrome/data/v1` |
| media | Deployment/prowlarr | retained-state | prowlarr /config config | 1000:1000 | `/config/.homelab-prowlarr-config` | `homelab/prowlarr/config/v1` |
| media | Deployment/qbittorrent | retained-data | qbittorrent /retained | 1000:1000 | `/retained/.homelab-qbittorrent-data` | `homelab/qbittorrent/data/v1` |
| media | Deployment/qbittorrent-ru | retained-data | qbittorrent-ru /retained | 1000:1000 | `/retained/.homelab-qbittorrent-ru-data` | `homelab/qbittorrent-ru/data/v1` |
| media | Deployment/radarr | retained-state | radarr /retained | 1000:1000 | `/retained/.homelab-radarr-data` | `homelab/radarr/data/v1` |
| media | Deployment/radarr-ru | retained-state | radarr-ru /retained | 1000:1000 | `/retained/.homelab-radarr-ru-data` | `homelab/radarr-ru/data/v1` |
| media | Deployment/seerr | retained-state | seerr /app/config config | 1000:1000 | `/app/config/.homelab-seerr-config` | `homelab/seerr/config/v1` |
| media | Deployment/seerr-ru | retained-state | seerr-ru /app/config config .homelab-seerr-config | 1000:1000 | `/app/config/.homelab-seerr-config` | `homelab/seerr-ru/config/v1` |
| media | Deployment/shelfmark | retained-state | shelfmark /retained | 1000:1000 | `/retained/.homelab-shelfmark-data` | `homelab/shelfmark/data/v1` |
| media | Deployment/sonarr | retained-state | sonarr /retained | 1000:1000 | `/retained/.homelab-sonarr-data` | `homelab/sonarr/data/v1` |
| media | Deployment/sonarr-ru | retained-state | sonarr-ru /retained | 1000:1000 | `/retained/.homelab-sonarr-ru-data` | `homelab/sonarr-ru/data/v1` |
| monitoring | Alertmanager/kube-prometheus-stack-alertmanager | retained-state | alertmanager /data | 1000:2000 | `/data/.homelab-alertmanager-data` | `homelab/alertmanager/data/v1` |
| monitoring | Deployment/kube-prometheus-stack-grafana | grafana-retained-state | grafana /var/lib/grafana | 472:472 | `/var/lib/grafana/.homelab-grafana-data` | `homelab/grafana/data/v1` |
| monitoring | Prometheus/kube-prometheus-stack-prometheus | retained-state | prometheus /data | 1000:2000 | `/data/.homelab-prometheus-data` | `homelab/prometheus/data/v1` |
| monitoring | StatefulSet/loki | retained-state | loki /data | 10001:10001 | `/data/.homelab-loki-data` | `homelab/loki/data/v1` |
| monitoring | StatefulSet/tempo | retained-state | tempo /data | 10001:10001 | `/data/.homelab-tempo-data` | `homelab/tempo/data/v1` |
| operations | Deployment/bytestash | retained-data | bytestash /retained | 0:0 | `/retained/.homelab-bytestash-data` | `homelab/bytestash/data/v1` |
| operations | Deployment/changedetection | retained-data | changedetection /retained | 0:0 | `/retained/.homelab-changedetection-data` | `homelab/changedetection/data/v1` |
| operations | Deployment/convertx | retained-convertx-data | convertx /retained | 0:0 | `/retained/.homelab-convertx-data` | `homelab/convertx/data/v1` |
| operations | Deployment/karakeep | retained-data | karakeep /retained | 0:0 | `/retained/.homelab-karakeep-data` | `homelab/karakeep/data/v1` |
| operations | Deployment/karakeep | retained-meilisearch | karakeep-meilisearch /retained | 0:0 | `/retained/.homelab-karakeep-meilisearch-data` | `homelab/karakeep-meilisearch/data/v1` |
| operations | Deployment/microbin | retained-data | microbin /retained | 0:0 | `/retained/.homelab-microbin-data` | `homelab/microbin/data/v1` |
| operations | Deployment/ntfy | retained-state | ntfy /var/cache/ntfy | 1001:1001 | `/var/cache/ntfy/.homelab-ntfy-data` | `homelab/ntfy/data/v1` |
| operations | Deployment/paperless-ngx | retained-data | paperless /retained | 1000:1000 | `/retained/.homelab-paperless-data` | `homelab/paperless/data/v1` |
| operations | Deployment/stirling-pdf | retained-data | stirling-pdf /retained | 1000:1000 | `/retained/.homelab-stirling-pdf-data` | `homelab/stirling-pdf/data/v1` |

Jellyfin (`/config/.homelab-jellyfin-data`) and filebrowser (`/home/filebrowser/data/.homelab-filebrowser-data`) carry
markers but are not wired to the guard yet.
