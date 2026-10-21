# Oleg Commander

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

Проект реализует защиту от:
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
oleg-commander logs           # Журнал действий
oleg-commander approvals      # Запросы на одобрение
oleg-commander approve <id>   # Одобрить запрос
oleg-commander reject <id>    # Отклонить запрос
```

## Подключение MCP-клиента

### Для локального использования:
```bash
oleg-commander start
# Затем подключайтесь через stdin к выбранному клиенту.
```

### Для удалённого подключения:
Для использования с ChatGPT или другими MCP клиентами через HTTP:

1. Настройте SSL-сертификат
2. Включите аутентификацию в конфигурации
3. Используйте endpoint `/mcp` 

## Примеры использования

1. Прочитать файл из ~/Develop:
```bash
oleg-commander execute filesystem.read_file --path ~/Develop/README.md
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