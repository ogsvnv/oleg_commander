# Oleg Commander

> **Статус: прототип.** Не используйте для удалённого администрирования в
> недоверенной сети. SSH/SFTP реализованы через AsyncSSH; чтение данных systemd,
> Docker и процессов выполняется через ограниченные системные команды. Удаление
> процессов пока отключено. Изменяющие операции при `require_approval: true`
> требуют отдельного разрешения через **локальный CLI**.
> HTTP доступен только на loopback (без внешнего подключения).
> Следующие задачи — [issue #1](https://github.com/ogsvnv/oleg_commander/issues/1).

## 🔐 Подтверждения и аудит (локальный CLI)

По умолчанию `security.read_only: true`, поэтому любые изменяющие
операции запрещены без возможности подтверждения. Для режима с запросом
разрешений **в доверенной локальной среде** укажите:

```yaml
security:
  read_only: false
  require_approval: true
logging:
  audit_enabled: true
```

При попытке изменить файл, выполнить опасную команду SSH/терминала,
создать коммит или перезапустить службу MCP возвращает
`APPROVAL_REQUIRED` и уникальный `approval_id`, но ничего не выполняет.

**Только владелец локальной учётной записи** открывает отдельный терминал:

```bash
oleg-commander approvals          # запросы, цели и короткие отпечатки аргументов
oleg-commander approve <id>       # разрешить одну точную операцию
oleg-commander reject <id>        # отклонить
oleg-commander logs --limit 20    # аудит без содержимого файлов и команд
```

После разрешения MCP-клиент **повторяет тот же вызов с теми же аргументами**.
Подтверждение действует 10 минут и расходуется один раз. Любое изменение
аргументов требует нового разрешения. Подтверждения записываются в SQLite,
а аудит — JSONL в `~/.local/state/oleg-commander/` (права владельца).
Там сохраняются хеши аргументов и безопасные обозначения целей, **но не
содержимое файлов, команды с аргументами, stdout/stderr или токены**.
Содержимое журналов служб может содержать секреты — ограничьте доступ.

В MCP **нет инструментов** `approve`/`reject`: решения принимаются
вне ИИ через CLI. Это дополнительный барьер для локального использования,
но не замена аутентификации для публичного HTTP. Пока HTTP ограничен localhost.
При `audit_enabled: false` изменяющие операции блокируются.

## Ограничения локальной файловой системы

При отсутствии `security.allowed_directories` **доступ к локальным файлам
запрещён**, даже если сервер запущен из домашнего каталога. Добавьте только
нужные рабочие каталоги в `config.yaml`, например:

```yaml
security:
  allowed_directories:
    - /home/ogsvnv/Develop
```

Операции чтения/записи/редактирования, поиск и обход каталогов выполняются
относительно открытых файловых дескрипторов разрешённых каталогов. Не допускается
переход по символическим ссылкам (включая промежуточные компоненты пути).
Запись и редактирование используют временные файлы и атомарную замену внутри
разрешённого каталога. Для записи требуется существующий родительский каталог:
создайте его предварительно отдельной операцией `filesystem.create_directory`.

Чтение и отдельная запись ограничены `execution.max_output_bytes` (не более
этого значения на файл), `read_multiple_files` — максимум 20 путей и один
совокупный лимит вывода. Обход каталогов ограничен числом просмотренных записей,
глубиной и временем. Списки результатов не бесконечные, полное индексирование
дерева файлов не поддерживается. Эти ограничения являются защитой от случайной
нагрузки, но **не заменяют** изоляцию отдельного Unix-пользователя.
Остаётся риск гонки при **одновременной** записи другим процессом внутри
того же каталога: перед редактированием проверяются метаданные, но не все
сценарии конкурентной замены устранены. Не давайте доступ к каталогам,
которые одновременно контролирует недоверенный локальный процесс.

## Настройка SSH

`config.example.yaml` — **пример**, не активная конфигурация.
Создайте файл `config.yaml` в рабочем каталоге или укажите
`OLEG_COMMANDER_CONFIG=/путь/к/конфигурации.yaml`.

```bash
cp config.example.yaml config.yaml
# Проверьте host aliases в ~/.ssh/config и доверенные ключи:
ssh park
# Вручную сверяйте отпечаток SSH-ключа с надёжным источником.
.venv/bin/oleg-commander doctor
```

- `allowed_ssh_hosts` — список SSH-алиасов; пустой запрещает SSH.
- `allowed_ssh_directories` — абсолютные каталоги **для каждого хоста**;
  пустой список запрещает доступ к удалённым файлам.
- Сервер сверяет SSH-ключ с `~/.ssh/known_hosts`; отключения проверки нет.
- `ssh.execute` в защищённом режиме допускает только
  `date`, `hostname`, `pwd`, `uname`, `uptime`, `whoami` без аргументов.
- Запись, загрузка и скачивание файлов доступны только при
  `read_only: false` **и** `require_approval: false`. До реализации
  подтверждений использовать такой режим только в доверенной среде.
- Запись на SSH-сервер использует временный файл и POSIX rename; сервер
  должен поддерживать расширение `posix-rename@openssh.com`.
- Объём файлов ограничен `execution.max_output_bytes`, время — `execution.timeout`.
- Подключения SSH временные: закрываются после каждой операции.

## Локальная диагностика (systemd / Docker / процессы)

Для журналов и сведений о контейнерах необходимо указать точные имена в
`security.allowed_systemd_services` и `security.allowed_docker_containers`.
Если список пуст — доступ запрещён. Пример:

```yaml
security:
  read_only: true
  require_approval: true
  allowed_systemd_services: [ollama.service]
  allowed_docker_containers: [my_app]
```

Доступны `systemd.status`, `systemd.logs`, `docker.ps`,
`docker.logs`, `docker.inspect`, `process.list`, `process.info`.
Просмотр Docker-контейнеров фильтруется по разрешённым именам, а
`docker.inspect` возвращает только имя, образ и состояние без переменных
окружения. `ps` не возвращает аргументы или переменные окружения процессов.

Журналы могут содержать секреты, поэтому включайте их только для доверенных
служб и контейнеров. Общий вывод ограничен
`execution.max_output_bytes`, время выполнения — `execution.timeout`.
Перезапуск systemd и Docker требует явного отключения `read_only` и
`require_approval` (не рекомендуется без отдельного защищённого окружения).
`process.kill` не реализован.

## Быстрый запуск

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/oleg-commander doctor
.venv/bin/oleg-commander start
# Локальный HTTP (только 127.0.0.1):
.venv/bin/oleg-commander start --transport http
```

По умолчанию доступен только безопасный режим: чтение файлов в разрешённых
каталогах, операции чтения Git и ограниченные команды терминала без аргументов.
Для разрешённой записи установите `read_only: false` и оставьте
`require_approval: true`, чтобы каждое изменение требовало локального решения.


Oleg Commander — это собственный аналог Desktop Commander для удалённого управления компьютерами через Model Context Protocol (MCP).

## Назначение

Предоставляет AI-ассистентам безопасный доступ к:
- локальной файловой системе;
- терминалу Linux;
- SSH-серверам;
- Git-репозиториям;
- Python/Django-проектам;
- системным процессам;
- системным журналам;
- Docker;
- systemd.

## Установка

```bash
# Для разработки
pip install -e .

# Или с использованием uv (если установлен)
uv pip install -e .
```

## Запуск

```bash
# Запуск локально через stdin (для тестирования)
oleg-commander start

# Запуск через HTTP (на 127.0.0.1:8765)
oleg-commander start --transport http
```

## Архитектура

```
oleg_commander/
├── pyproject.toml
├── README.md
├── .gitignore
├── config.example.yaml
│
├── src/oleg_commander/
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py        # Основной сервер MCP
│   ├── config.py        # Конфигурация
│   ├── security.py      # Модуль безопасности
│   ├── audit.py         # Аудит действий
│   ├── cli.py           # CLI интерфейс
│   │
│   ├── tools/           # MCP инструменты
│   │   ├── __init__.py
│   │   ├── filesystem.py   # Файловая система
│   │   ├── terminal.py     # Терминал
│   │   ├── ssh.py          # SSH
│   │   ├── git.py          # Git
│   │   ├── processes.py    # Процессы
│   │   ├── systemd.py      # Systemd
│   │   └── docker.py       # Docker (опционально)
│   │
│   └── services/        # Службы
│       ├── __init__.py
│       ├── path_service.py
│       ├── command_service.py
│       ├── ssh_service.py
│       └── approval_service.py
│
├── tests/               # Тесты
│   ├── conftest.py
│   ├── test_basic.py     # Базовые тесты
│   └── ...
│
└── deployment/
    └── oleg-commander.service  # systemd service файл
```

## Поддерживаемые инструменты

### Файловая система
- `filesystem.list_directory` - Список файлов и директорий
- `filesystem.read_file` - Чтение файла
- `filesystem.write_file` - Запись файла
- `filesystem.edit_file` - Точечная замена текста
- `filesystem.search_files` - Поиск файлов по имени
- `filesystem.search_content` - Поиск содержимого в файлах
- `filesystem.get_file_info` - Информация о файле
- `filesystem.create_directory` - Создание директории
- `filesystem.move_file` - Перемещение файла
- `filesystem.copy_file` - Копирование файла
- `filesystem.delete_file` - Удаление файла

### Терминал
- `terminal.execute_command` - Выполнение команды

### SSH
- `ssh.list_hosts` - Список разрешённых хостов
- `ssh.connect` - Проверка подключения
- `ssh.execute` - Выполнение команды на удалённом сервере
- `ssh.read_file` - Чтение файла на удалённом сервере
- `ssh.write_file` - Запись файла на удалённом сервере

### Git
- `git.status` - Статус репозитория
- `git.diff` - Изменения
- `git.log` - История коммитов
- `git.branches` - Ветки
- `git.current_branch` - Текущая ветка
- `git.create_branch` - Создание ветки
- `git.add` - Добавление файлов
- `git.commit` - Коммит
- `git.pull` - Загрузка изменений
- `git.push` - Отправка изменений

### Системные процессы и службы
- `process.list` - Список процессов
- `systemd.status` - Статус сервиса
- `systemd.logs` - Логи сервиса
- `docker.ps` - Список контейнеров (опционально)

## Безопасность

Следующие средства защиты запланированы или частично реализованы:
- Path traversal атак
- Проверки подлинности SSH-хостов 
- Ограничения доступа к каталогам
- Требования подтверждения опасных операций
- Ограничения времени выполнения команд

## Конфигурация

Файл конфигурации `config.example.yaml`:

```yaml
server:
  name: Oleg Commander
  transport: stdio
  host: 127.0.0.1
  port: 8765

security:
  read_only: true
  require_approval: true

  allowed_directories:
    - /home/ogsvnv/Develop

  allowed_ssh_hosts:
    - zalman1
    - wob
    - gamma-1

execution:
  timeout: 30
  max_output_bytes: 1048576

logging:
  level: INFO
  audit_enabled: true
```

## Использование CLI

```bash
oleg-commander start          # Запуск сервера
oleg-commander doctor         # Диагностика системы
oleg-commander status         # Статус сервера  
\# Остальные команды CLI пока не реализованы
```

## Подключение MCP-клиента

### Для локального использования:
```bash
oleg-commander start
# Затем подключайтесь через stdin к выбранному клиенту.
```

### Для удалённого подключения:
Прямой доступ из ChatGPT через публичный HTTP **пока не поддерживается**:
нужны проверенная аутентификация, HTTPS и отдельная модель доверия.
Локальный HTTP использует endpoint `/mcp`. 

## Примеры использования

1. Прочитать файл из ~/Develop:
```bash
\# Примеры ниже — целевой формат, команда execute пока не реализована
```

2. Найти код функции в Django-проекте:
```bash
oleg-commander execute filesystem.search_content --path ~/Develop/myproject --query "def my_function"
```

3. Выполнить pytest:
```bash
oleg-commander execute terminal.execute_command --executable pytest --args ["--verbose"]
```

4. Посмотреть git diff:
```bash
oleg-commander execute git.diff --path ~/Develop/myproject
```

5. Подключиться к zalman1:
```bash
oleg-commander execute ssh.connect --host zalman1
```

6. Посмотреть systemd-журнал Ollama:
```bash
oleg-commander execute systemd.logs --service ollama.service
```

7. Запросить безопасное изменение настроек: 
   - Сервер запросит подтверждение через CLI интерфейс

8. Получить подтверждение пользователя:
   - Через CLI команды approve/reject

9. Выполнить разрешённую операцию:
   - После одобрения сервер выполнит действие

10. Проверить результат:
    - Возвращается успешный или неудачный результат с подробной информацией

## Развёртывание через systemd

Чтобы автоматически запускать сервис при загрузке:

```bash
# Скопируйте файл сервиса в системную директорию
sudo cp deployment/oleg-commander.service /etc/systemd/system/

# Перезагрузите systemctl
sudo systemctl daemon-reload

# Включите автозапуск
sudo systemctl enable oleg-commander.service

# Запустите сервис
sudo systemctl start oleg-commander.service

# Проверьте статус
sudo systemctl status oleg-commander.service
```

## Требования

- Python 3.11+
- Операционная система: Ubuntu Linux
- Пользователь: ogsvnv

## Документация по подключению к ChatGPT

См. файл [docs/chatgpt_setup.md](docs/chatgpt_setup.md) для подробной информации о подключении через удалённый MCP.