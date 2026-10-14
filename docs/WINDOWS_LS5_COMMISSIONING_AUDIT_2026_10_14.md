# Безопасная подготовка Windows / LS5 — 14.10.2026

**Статус: код подготовки реализован, развёртывание LS5 заблокировано до отдельного подтверждения и устранения перечисленных ограничений.** Ни постоянные службы, ни задачи, ни торговля, ни Telegram не запускались. Существующие установки, credentials, runtime gate и PostgreSQL не изменялись. SQL на LS5 выполнялся только через соединение/транзакцию read-only; запрос завершился отказом в правах.

## Зафиксированные исходники

| Компонент | SHA / связь |
|---|---|
| Grid main | `d537d525296ef34f727996e240ae6c60102c6082` |
| Grid composed #180 | `a79ee1234b082f84dae9226a0b8cdfa0025a0249` |
| Grid #181, основа новой ветки | `061e28c6b3062a545997b319a05870b07d164f63` |
| Новая Grid-ветка | `audit/codex-ls5-safe-commissioning-20261014`, PR на ветку #181 |
| Strattester main / проверка контрактов | `37ff7e9d12a4d2dccd788fc493c28557dbe8bcea` |
| Terminan main | `fee79f4b15fc1f9efcff9ca12c403688b0026260` |
| Terminan новый Draft [#5](https://github.com/YehorBabenko88/Terminan/pull/5) | `c711f9ce13678e3777c9707a2f34b5c30ce2dbb8`, `audit/codex-ls5-port-20261014` |

Исправления #181 включены через ancestry, а не переписаны: retention schema создаётся до запуска фоновых задач; пустая таблица больше не создаёт phantom backlog по EXPLAIN. Исходные PR/пользовательские ветки не редактировались. Финальный Grid SHA и Actions IDs указаны в новом PR и приложенном итоговом evidence: отслеживаемый файл не может включить SHA собственного будущего коммита.

## Подтверждённые дефекты и изменения

| Уровень | Воспроизведение / причина | Исправление / проверка |
|---|---|---|
| P1 | Ownership manifest имел допустимый `root`, но чужой `data`; конфигуратор изменял чужой `postgresql.conf` | Точное соответствие root/data каталогу Grid, boolean ownership, запрет reparse points по всем родителям. Красный fixture до исправления, зелёный после; только временные файлы |
| P1 | install.ps1 сразу регистрировал/запускал SYSTEM-задачи, удалял задачи другой роли и запускал standalone ArchivePipeline, уже заблокированный #178 | Default PLAN_ONLY; `-Apply` явно, только disabled tasks, existing tasks блокируют подготовку без удаления/замены; архивная задача не регистрируется; активация отдельная. Fixture до исправления фиксировал мутацию |
| P2 | Повторная конфигурация PostgreSQL всегда переписывала файл и рестартовала службу | План по умолчанию; отдельные Apply/Restart, no-op при неизменном конфиге, exclusive mutex, fsync временного файла, atomic replace с сохранением старого конфига; restart дополнительно проверяет image/data службы |
| P2 | Staging выбирал любую старую успешную проверку, даже если более новая проверка того же SHA красная; audit-ветка не поддерживалась | Проверяется последняя проверка каждого workflow на точном SHA/ветке; для audit-ветки обязательны пять workflow; cancelled/skipped/pending/failure блокируют staging |
| P2 | CONTROL и Terminan одновременно занимали порт 8765, Terminan игнорировал настройку другого порта | Отдельный Terminan #5: проверенный TERMINAN_PORT, default 8765 сохранён, для совместного размещения выбрать 8766. Loopback и read-only сохранены; mock server, реальный listener не запускался |

Старые два source-теста service placement положительно требовали запуска standalone ArchivePipeline. Они заменены строгими проверками запрета регистрации/старта архива, старта любых задач и удаления существующих задач. Это намеренное изменение контракта подготовки, а не ослабление safety gate.

### Новый preflight

`installer/windows_preflight.py` — одноразовая проверка, JSON + exit 0/2, **activation_authorized=false всегда**.

* Проверяет release manifest, точный SHA, SHA-256 файлов, coverage Python source и обязательные fencing-файлы; отказывает при traversal/junction/symlink, дубликатах путей, неизвестном runtime Python. Hash-цикл ограничен 60 секундами, manifest — 32 MiB; timeout означает BLOCKED, а не частичный успех.
* Python 3.11/3.12: изолированные import smoke и `pip check`, stdout/stderr дочерних процессов не публикуются. Импорт Coordinator не запускает startup/службы. Checker запускается с `-B`, не компилирует установленные source-файлы.
* Проверяет наличие credentials своей роли (worker: env либо штатный secrets/node.credential, без вывода содержимого), отсутствие настроенного Telegram/trading credentials и явное `RETENTION_ENABLED=false` для commissioning. Ничего не исправляет в `.env` автоматически.
* `--check-db` допускает URL только базы `bybit_cluster_grid`, подключается с `default_transaction_read_only=on`, statement/lock/connect timeout, явной read-only транзакцией. Проверяет полный каталог 1–47, наличие retention/ownership таблиц и ключевых типов колонок, gate только INFRA_ONLY/PAUSED/STOPPED. Нет DDL, migration apply, очистки, reset gate или запросов к чужим базам.
* `--smoke-url` делает только GET `/health`, без redirects, bounded body/timeout. Требует действующий quiescent CONTROL leader. ACTIVE, follower, missing/unknown gate и недоступность блокируют проверку; `/start` не вызывается.
* Исключения представлены code + class; DSN, пароли, токены, текст исключений, сырые HTTP bodies, environment и командные строки процессов не выводятся.

`installer/rollback-release.ps1` планирует pointer rollback через существующий journal/mutex switch-release. Требует явно выбранный reviewed SHA, проверяет release/схему/gate и disabled tasks/no Grid process. `-Apply` меняет только pointer через switch-release; не делает schema downgrade, не очищает WAL, не удаляет старую установку и не запускает задачи. Недоступность Scheduler/CIM блокирует процедуру. Это подготовленный инструмент, он не выполнялся на реальной установке.

### Артефакт и зависимости

Windows bundle теперь checkout-ит именно PR HEAD; имя ZIP, manifests и artifact используют этот же SHA, а не временный merge-ref. `runtime-packages.json` фиксирует версии установленного изолированного runtime и попадает в SHA-256 manifests. Linux pytest и внешние контракты продолжают выполняться независимо.

`requirements.txt` по-прежнему задаёт нижние границы. Это не полностью хешированный lock; новая сборка позднее может получить новые transitive версии. Развёртывать можно только конкретный уже проверенный артефакт с проверенным SHA-256 и inventory runtime, а не заново `pip install -r requirements.txt` на LS5/system Python. Полная supply-chain аттестация/хешированный offline wheelhouse остаётся ограничением. ML runtime изолируется существующим bootstrap-ml; его настройка на LS5 не запускалась.

## Фактическая read-only диагностика LS5

| Проверка | Наблюдение |
|---|---|
| Текущий установленный SHA | `9ab1f5b85ec471ea21ec89f1b76740c0b01537b6` |
| Previous SHA | `2017ed4fd16b0b222173a6d42b5bf24b2beb73ac` |
| Старый release / новый протокол | `RELEASE_PROTOCOL_FILES_MISSING`; автоматический rollback к нему не одобрен |
| Зависимости проверяющего workspace Python | PASS, Python 3.12.14; это не доказательство зависимостей текущего SYSTEM runtime |
| Диск для release | `DISK_HEADROOM_READY` |
| CONTROL localhost:8765 | `CONTROL_UNAVAILABLE` / ClientConnectorError; не запускался |
| База Grid | `DATABASE_UNAVAILABLE` / InsufficientPrivilegeError; версия/retention/gate неизвестны, нельзя считать их проверенными |
| Admin token | `ROLE_CREDENTIAL_MISSING`; никакой token не создавался |
| Retention commissioning switch | `RETENTION_DISABLE_REQUIRED`; ничего не переключалось |
| Telegram | `TELEGRAM_CONFIGURED`; существующий token не выводился и не активировался/удалялся |
| Trading credentials | `NO_TRADING_CREDENTIALS` для проверенной конфигурации, реальных сделок нет |
| Windows Task Scheduler | CIM access unavailable; пустой список не считается доказательством отсутствия задач |
| Tailscale local API | Access denied к защищённому named pipe; служба/ACL не изменялись |
| SSH discovery | known_hosts чтение получило OS PermissionError даже после session read permission; ключи не читались, remote-команды не запускались |

В `Documents/Codex/Deployment-LS5` есть отдельная подготовленная копия; её наличие не доказывает активацию. Текущие ProgramFiles/ProgramData установки сохранены. Нет доказанного inventory других ПК или успешного SSH/failover: это BLOCKER, а не обещание доступности сети.

## Три репозитория / ограничения совместимости

Проверяются реальные модули scientific export/handoff Strattester, исторический importer Grid и read-only adapters Terminan; десять сетево-запрещённых тестов закрепляют SHA, timestamps, hashes, historical-only capabilities, отсутствие LIVE promotion и SQLite read-only. Terminan PG adapter проверяется синтетическим соединением с read-only options; реальные production role permissions неизвестны.

Strattester использует Python >=3.11, отдельную среду и собственные service intents. Его `service/install_windows.ps1` удаляет/перерегистрирует и запускает службы — **не использовать для этого задания**. Ops purge/quarantine/bootstrap также не вызываются. Для Strattester отдельный PR не нужен: в проверенном контракте дефект не подтверждён. Terminan остаётся loopback-only; порт 8766 выбирается только при отдельном будущем запуске, не в текущей сессии.

## Тесты и CI

Локально Windows Python3.12: **1178 passed, 29 skipped, 7 subtests passed**, 4 известных FastAPI deprecation warnings. Пять PG-only модулей исключены локально, другие PG тесты skip без DSN. Это не полный PostgreSQL результат.

```powershell
$env:TEMP=(Resolve-Path '..').Path
$env:TMP=$env:TEMP
$env:ProgramData=Join-Path $env:TEMP 'test-programdata'
$env:GRID_SHARED_TOKEN='test-token'
$env:GRID_REQUIRE_COMPOSED_GATES='1'
$env:AUDIT_GRID_ROOT=(Get-Location).Path
$env:AUDIT_STRATTESTER_ROOT=(Resolve-Path '..\strattester-composed-contract').Path
$env:AUDIT_TERMINAN_ROOT=(Resolve-Path '..\terminan-ls5-port').Path
..\venv\Scripts\python.exe -m pytest -q --ignore=tests/test_server_pilot_postgres_integration.py --ignore=tests/test_enrollment_postgres_integration.py --ignore=tests/test_floating_leader_postgres_race.py --ignore=tests/test_ml_dispatch_lock_postgres.py --ignore=tests/test_ml_lease_lifecycle_postgres.py
pwsh -NoProfile -File installer/tests/test-safe-postgres-config.ps1
pwsh -NoProfile -File installer/tests/test-install-plan.ps1
pwsh -NoProfile -File installer/tests/test-rollback-plan.ps1
pwsh -NoProfile -File installer/tests/test-audit-stage.ps1
```

Fixtures используют только собственные временные файлы и mocked OS/GitHub providers. В PostgreSQL CI новый `test_windows_preflight_postgres.py` создаёт отдельную случайную schema disposable PG16: fresh migrations, retention init, сохранность sentinel candle, repeated ensure/migration, read-only checker, сохранение уже ACTIVE gate без reset. Дополнительный поведенческий тест запрещает создание Coordinator services при отказе retention schema.

Обязательные workflow: preflight (Linux 3.11/3.12, полный pytest/PG16), windows-bundle (existing matrices + новые unit checks), commissioning-manifest, composed-safety-gate, windows-commissioning (mocked fixtures PS7 и PS5.1). Для Terminan #5 — собственный Python CI. Финальные run IDs, HEAD и результаты публикуются в PR/evidence после завершения; старые зелёные PR180 не заменяют новые проверки.

## Точные команды LS5 — только диагностика/план, без deployment

В новом PowerShell окне; не включать transcript, verbose HTTP/SSH или echo `.env`.

```powershell
$Source='C:\Users\LS-5\Documents\Codex\2026-10-13\codex-bybit-cluster-grid-yehorbabenko88-bybit\work\ls5-commissioning'
$Python='C:\Users\LS-5\Documents\Codex\2026-10-13\codex-bybit-cluster-grid-yehorbabenko88-bybit\work\venv\Scripts\python.exe'
$CandidateSha=(& git -C $Source rev-parse HEAD).Trim()
$InstalledSha=(Get-Content -LiteralPath "$env:ProgramFiles\BybitClusterGrid\current.version" -Raw).Trim()
& $Python -B "$Source\installer\windows_preflight.py" --release-dir "$env:ProgramFiles\BybitClusterGrid\releases\$InstalledSha" --expected-sha $InstalledSha --env-file "$env:ProgramData\BybitClusterGrid\.env" --check-db --smoke-url http://127.0.0.1:8765
# Exit 2 / BLOCKED ожидается, пока описанные проблемы не решены; не обходить.
& "$Source\installer\install.ps1" -ReleaseDir $Source -Python $Python -Mode CONTROL
# PLAN_ONLY; не создаёт файлы, задачи или службы.
& "$Source\installer\stage-github-release.ps1" -Branch audit/codex-ls5-safe-commissioning-20261014 -Commit $CandidateSha -AllowAuditCandidate
# Только GitHub API discovery; без -Download ничего не записывает.
& "$Source\installer\collect-commissioning-inventory.ps1"
# Не выводит CommandLine/environment/секреты; недоступный CIM означает unknown.
```

Для окна с разрешённым доступом к существующим Tailscale/Scheduler, без изменения ACL:

```powershell
Get-ScheduledTask -ErrorAction Stop | Where-Object TaskName -Like '*Grid*' | Select-Object TaskName,State
$Tailnet=& "$env:ProgramFiles\Tailscale\tailscale.exe" status --json | ConvertFrom-Json
$Tailnet.Peer.PSObject.Properties.Value | Select-Object HostName,Online,TailscaleIPs
# Для уже известного и проверенного SSH alias:
# ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o ConnectTimeout=3 ALIAS hostname
```

Не подставлять неизвестный alias/пользователя и не отключать host-key verification. Удалённые диагностики пока не выполнены из-за доступа; адреса/credentials не угадываются.

### После отдельного подтверждения (не выполнялось)

Только после backup/restore rehearsal, quiescent gate, пустого Telegram в **новой согласованной конфигурации**, retention=false, role permissions, полного inventory и успешного CI:

1. Скачать точный artifact в новый staging каталог через `stage-github-release.ps1 ... -Download -StageRoot <новый согласованный каталог>`. Существующий staging не перезаписывается. Проверить ZIP checksum и manifest SHA, не считать старую копию новым артефактом.
2. Отдельно согласовать extraction/install root, protected env/ACL и Grid-owned PostgreSQL. Не запускать legacy `bootstrap.ps1`, `provision_postgres.ps1`, `install-postgres.ps1` или Strattester installer: их автоматический repair/cleanup/service start выходит за текущие ограничения. Новая схема не применяется preflight-ом; сначала migration rehearsal на disposable копии, затем отдельное разрешение на Grid DB.
3. Повторить preflight с **Python из артефакта**, release manifest SHA и новой согласованной конфигурацией. Лишь после отдельного одобрения допускается `install.ps1 -Apply`; он регистрирует disabled task и ничего не запускает. Existing Grid task блокирует этот путь: сначала нужен отдельно проверенный upgrade, без удаления старой установки.
4. Активация CONTROL/Task Scheduler остаётся самостоятельным подтверждаемым этапом; StartServices намеренно отказан. Ни автоматического Telegram START, ни изменения gate в ACTIVE нет.

## Rollback и оставшиеся BLOCKERS

* Старые current/previous SHA не одобрены для схемы47: автоматический возврат к ним запрещён. Выбрать явно reviewed fencing-compatible SHA и проверить manifest/source/CI; presence fencing-файлов не заменяет code review и доверие к artifact provenance.
* На отдельной копии выполнить план: `rollback-release.ps1 -ReviewedVersion <проверенный SHA> -Python <Python проверенной сборки> -InstallRoot <копия> -DataRoot <копия>`. Требуются disabled tasks/no processes и quiescent gate. `-Apply` меняет только release pointer через существующий журнал и разрешается отдельно; перед ним backup и проверка pending/switch journal. WAL, receipts, данные, migration ledger и старые releases сохраняются.
* Не понижать/удалять schema47, не чистить uncertain WAL, не менять чужой PostgreSQL, не останавливать неизвестный процесс ради прохождения проверки.
* Физический power-cut/Windows reboot, PG restore, фактический Tailscale/SSH failover и SYSTEM task permissions не доказаны. Ни процессные mocks, ни зелёный CI не доказывают production HA.
* DB quarantine retention/capacity из предыдущего аудита остаются открыты. Commissioning retention=false не является политикой долгосрочного хранения.
* Legacy bootstrap/provisioning остаются запрещёнными entrypoints для текущего сценария; полноценное автоматическое обновление существующей LS5 установки нельзя считать проверенным до закрытия access/schema/config/backup blockers.

Никакого merge, deployment, реального task start, изменения Telegram или торговли в этом этапе нет.

## Review и первый цикл CI

Независимый read-only reviewer подтвердил P2: file-only credential штатно enrolled worker ошибочно считался отсутствующим. Исправлено; тест был красным до изменения, после изменения проверяет непустой/пустой/отсутствующий файл и отсутствие секрета в JSON.

Первый HEAD `4aad0370b2b8e3acc5957c2e0dca2edb72832fe4`: preflight 38594309706, windows-bundle 38594309773, commissioning-manifest 38594309869 и composed-safety-gate 38594309819 прошли. Новый workflow 38594255270 был отклонён до запуска jobs: `matrix` недопустим в steps.shell. Диагностика actionlint v1.7.12 подтвердила точную строку 18; исправлено на отдельные literal-shell PS7/PS5.1 шаги, без удаления fixture. Повторный actionlint проходит.

Добавлен настоящий Apply-path fixture для elevated Windows CI: fake preflight failure не пишет файлы/задачи; success регистрирует только disabled CONTROL task; повторная подготовка не перезаписывает existing task. Все Scheduler cmdlets mocked, файлы только в новом fixture. Локально этот fixture не запускался: LOCAL_ELEVATED=False; его фактический результат проверяется в CI. Новая итоговая проверка обязательна на новом HEAD — перечисленные выше четыре зелёных run её не заменяют.
