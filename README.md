# Oleg Commander

**Статус: локальный Linux MCP-сервер (рабочий прототип).**
Инструменты: файловая система, SSH/SFTP, Git, терминал, Docker, systemd,
просмотр процессов, локальные подтверждения и аудит действий.

> **Важно:** публичный HTTP и удалённая аутентификация пока не реализованы.
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
`terminal.start_process`, аутентифицированный внешний MCP HTTP.
Эти инструменты могут оставаться в списке MCP, но возвращают ошибку,
а не фиктивный успех.

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
oleg-commander start --transport http # только локальный loopback, без внешней аутентификации
oleg-commander doctor
oleg-commander status
oleg-commander approvals
oleg-commander approve <id>
oleg-commander reject <id>
oleg-commander logs --limit 20
```

Команды `oleg-commander execute`, `deploy`, `install` и
автоматический `systemd`-деплой **не реализованы**.

Для удалённого подключения необходим отдельный этап с HTTPS и
аутентификацией; не публикуйте порт 8765 и не проксируйте его наружу.
Локальный HTTP доступен лишь на `127.0.0.1` или `::1` и может
использоваться другими локальными процессами — для изоляции
предпочтителен **stdio**.

## Тесты и Issue

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/oleg_commander/config.py
```

Тесты GitHub Actions проверяют регрессионные сценарии SSH, файлов,
подтверждений и реальный in-memory цикл MCP
`initialize → list_tools → call_tool`. **CI не заменяет**
проверку при реальном запуске на Lenovo, SSH и Docker.

Открытые задачи: [Issue #1](https://github.com/ogsvnv/oleg_commander/issues/1).
