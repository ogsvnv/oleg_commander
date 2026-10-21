# Oleg Commander

**Статус: локальный Linux MCP-сервер (рабочий прототип).**
Инструменты: файловая система, SSH/SFTP, Git, терминал, Docker, systemd,
просмотр процессов, локальные подтверждения и аудит действий.

> **Важно:** удалённый доступ поддерживает только HTTPS со статическим
> Bearer-токеном. OAuth для клиентов, которым он обязателен, пока не реализован.
> Службы Docker/systemd, доступ к каталогам и SSH-хостам требуют явных
> разрешённых списков. Не запускайте сервер с правами root. Режим чтения
> включён по умолчанию. Проект требует проверки на реальных хостах.

## Установка (Ubuntu Linux, Python 3.11+)

```bash
git clone https://github.com/ogsvnv/oleg_commander.git
cd oleg_commander
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp config.example.yaml config.yaml
# Отредактируйте локальный config.yaml под ваши пути/хосты.
.venv/bin/oleg-commander doctor
.venv/bin/python -m pytest -q
```

`config.yaml` не коммитится в Git; для запуска в другом каталоге
укажите `OLEG_COMMANDER_CONFIG=/полный/путь/config.yaml`. При явном
указании отсутствующего файла загрузка прекращается.

Пример конфигурации для MCP-клиента, запускающего сервер по **stdio**:

```json
{
  "mcpServers": {
    "oleg-commander": {
      "command": "/путь/к/oleg_commander/.venv/bin/oleg-commander",
      "args": ["start"]
    }
  }
}
```

Проверка CLI: `oleg-commander start` принимает соединение через stdio;
прямой ввод команд в этом терминале не предусмотрен.

## Фактически реализовано

| Инструменты | Возможности |
|---|---|
| `filesystem.*` | Чтение, запись, правка, поиск, список, копирование, перемещение, удаление |
| `ssh.*` | Проверяемый SSH, ограниченный SFTP, команды |
| `git.*` | Status, diff, log, branches, локальные branch/add/commit |
| `terminal.execute_command` | Ограниченный subprocess без shell |
| `systemd.*` | Состояние, журнал, разрешённый перезапуск |
| `docker.*` | ps, logs, ограниченный inspect, разрешённый перезапуск |
| `process.*` | Список процессов, сведения по PID |

**Не поддерживаются:** `git.pull` / `git.push` (заблокированы до
верификации удалённых адресов), `process.kill`,
`terminal.start_process`, подключение с OAuth 2.0 (статический Bearer через HTTPS доступен).
Эти инструменты **не регистрируются в MCP** и не могут быть вызваны
удалённым MCP-клиентом. Отдельные внутренние методы также возвращают ошибку.

## Защита и разрешения

- `allowed_directories`: только явно указанные каталоги. Если список
  пуст, локальный доступ к файлам и запуск терминала запрещены.
  Операции файловой системы используют дескрипторы каталогов с
  `O_NOFOLLOW`, запрещают symlink, выход из корня и неподдерживаемые
  специальные файлы. Содержимое файлов ограничено
  `execution.max_output_bytes`.
- `terminal.execute_command`: в защищённом режиме — только `pwd`,
  `whoami`, `uptime`, `date`, `uname` без аргументов. Рабочий
  каталог должен быть внутри allowlist; применяются лимиты времени
  и общего объёма stdout+stderr. Произвольные команды возможны
  **только после отдельного разрешения** и с правами процесса сервера.
- `git.*`: репозиторий обязан содержать обычную директорию `.git` без
  symlink; вывод ограничен. Создание веток и коммитов — только с
  разрешением. Git worktrees с файлом `.git` пока не поддерживаются.
  Remote pull/push отключены.
- `allowed_ssh_hosts` и `allowed_ssh_directories`: разрешённые
  SSH-хосты и каталоги SFTP задаются явно. Ключи проверяются через
  `~/.ssh/known_hosts`; сетевые подключения используют AsyncSSH.
  Неизвестный SSH-хост запрещён.
- `allowed_systemd_services` и `allowed_docker_containers`:
  разрешённые службы и контейнеры. По умолчанию списки пусты.
  Журналы могут содержать секреты — предоставляйте доступ осторожно.
- При одновременной модификации каталогов недоверенным локальным
  процессом остаются гонки; для сильной изоляции нужен отдельный
  Unix-пользователь и отдельные права файловой системы.

## Подтверждение операций

По умолчанию `read_only: true`, то есть запись полностью запрещена.
Для режима запросов у локального оператора используйте:

```yaml
security:
  read_only: false
  require_approval: true
logging:
  audit_enabled: true
```

Вызов, который изменяет состояние, сначала возвращает
`APPROVAL_REQUIRED` и `approval_id` **без выполнения действия**.
Локальный оператор в отдельном терминале проверяет цель и разрешает
**один** точный вызов:

```bash
oleg-commander approvals
oleg-commander approve <id>
oleg-commander reject <id>
oleg-commander logs --limit 20
```

После подтверждения клиент повторяет вызов с теми же аргументами.
Разрешение действует 10 минут и расходуется один раз. MCP-инструментов
для выдачи подтверждений нет. Записи аудита по умолчанию хранятся
в `~/.local/state/oleg-commander/` с ограниченными правами. В журнал
не попадают аргументы, содержимое файлов и вывод команд; он хранит
метаданные исхода операции. Для записи аудит обязателен.

**Осторожно:** разрешение произвольной команды даёт ей все права
операционной системы пользователя, от имени которого запущен сервер.
Не запускайте Oleg Commander от root.

## CLI

```bash
oleg-commander start                  # stdio MCP
oleg-commander start --transport http # только локальный loopback
oleg-commander start --transport https # TLS и Bearer, см. ниже
oleg-commander doctor
oleg-commander status
oleg-commander approvals
oleg-commander approve <id>
oleg-commander reject <id>
oleg-commander logs --limit 20
```

Команды `oleg-commander execute`, `deploy`, `install` и
автоматический `systemd`-деплой **не реализованы**.

Для удалённого подключения используйте только описанный ниже режим
`https` с Bearer-токеном. Локальный HTTP остаётся без внешней аутентификации
и доступен только на loopback; для изоляции предпочтителен **stdio**.

## HTTPS для удалённого подключения

`http` и `streamable-http` остаются доступны **только на loopback**.
Внешнее прослушивание разрешается лишь через `transport: https` со
статическим Bearer-токеном и серверным TLS:

```yaml
server:
  transport: https
  host: 0.0.0.0
  port: 8765
  public_host: commander.example.org
  tls_certfile: /etc/ssl/certs/commander.pem
  tls_keyfile: /home/user/.config/oleg-commander/key.pem
```

Сертификат должен соответствовать домену, быть выпущен доверенным центром,
а ключ — доступен только владельцу (`chmod 600`). **Не помещайте токен
в репозиторий или YAML.** Сгенерируйте криптографически случайный токен
вне истории shell и установите переменную `OLEG_COMMANDER_BEARER_TOKEN`
для процесса сервера. Требуется не менее 32 символов A–Z/a–z/0–9/_/-.

Для подключения укажите URL `https://commander.example.org:8765/mcp`
и HTTP-заголовок `Authorization: Bearer <токен>`. Все запросы,
включая GET/POST/DELETE, проходят проверку заголовка; также проверяются
Host и Origin. Отсутствующий или неверный токен отклоняется с кодом 401.

**Это режим для доверенных MCP-клиентов, умеющих отправлять статический
Bearer-заголовок.** Он не реализует OAuth 2.0 / динамическую регистрацию,
поэтому не заявляется совместимым с любым облачным клиентом, включая
ChatGPT. Для подключения через публичный интернет дополнительно
рекомендуются VPN, ограничение firewall и отдельная непривилегированная
учётная запись. HTTPS нельзя заменять проксированием открытого HTTP.

## Тесты и Issue

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/oleg_commander/config.py
```

Тесты GitHub Actions проверяют регрессионные сценарии SSH, файлов,
подтверждений и цикл MCP `initialize → list_tools → call_tool` как
в памяти, так и через реальный CLI-процесс по stdio. **CI не заменяет**
проверку при реальном запуске на Lenovo, SSH и Docker.

Открытые задачи: [Issue #1](https://github.com/ogsvnv/oleg_commander/issues/1).
