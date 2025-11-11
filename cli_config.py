# -*- coding: utf-8 -*-
"""
CLI配置模块 / Модуль конфигурации CLI / CLI Configuration Module

为所有测试脚本提供统一的命令行参数解析
Единый парсинг аргументов командной строки для всех тестовых скриптов
Unified command-line argument parsing for all test scripts

中文注释：CLI配置模块，统一管理命令行参数
Русский комментарий: Модуль конфигурации CLI для управления аргументами
"""

import argparse
from pathlib import Path
from typing import Optional


class CLIConfig:
    """
    CLI配置类 / Класс конфигурации CLI

    提供统一的命令行参数管理 / Единое управление аргументами
    """

    # 默认文件路径 / Пути по умолчанию / Default file paths
    DEFAULT_PATHS = {
        'authors_file': r'C:\istina\materia 材料\测试表单\authors.json',
        'dois_file': r'C:\istina\materia 材料\测试表单\dois.json',
        'crossref_authors': r'C:\istina\materia 材料\测试表单\crossref_authors.json',
        'crossref_articles': r'C:\istina\materia 材料\测试表单\crossref.json',
        'output': 'disambiguation_results.json',
        'report': 'disambiguation_report.md'
    }

    @staticmethod
    def create_base_parser(
        description: str,
        add_data_files: bool = True,
        add_output_files: bool = True,
        add_config: bool = True
    ) -> argparse.ArgumentParser:
        """
        创建基础参数解析器 / Создание базового парсера

        参数 / Параметры / Parameters:
            description: 程序描述 / Описание программы / Program description
            add_data_files: 是否添加数据文件参数 / Добавить параметры файлов данных
            add_output_files: 是否添加输出文件参数 / Добавить параметры выходных файлов
            add_config: 是否添加配置参数 / Добавить параметры конфигурации

        返回 / Возвращает / Returns:
            配置好的ArgumentParser / Настроенный ArgumentParser
        """
        parser = argparse.ArgumentParser(
            description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=CLIConfig._get_usage_examples()
        )

        # 输入数据文件参数 / Параметры входных файлов данных
        if add_data_files:
            data_group = parser.add_argument_group(
                'Входные данные / Input Data',
                'Параметры для указания путей к файлам данных'
            )

            data_group.add_argument(
                '--authors-file',
                type=str,
                default=CLIConfig.DEFAULT_PATHS['authors_file'],
                metavar='PATH',
                help=(
                    '作者JSON文件路径 / Путь к файлу authors.json / '
                    f'Path to authors.json file (default: {CLIConfig.DEFAULT_PATHS["authors_file"]})'
                )
            )

            data_group.add_argument(
                '--dois-file',
                type=str,
                default=CLIConfig.DEFAULT_PATHS['dois_file'],
                metavar='PATH',
                help=(
                    'DOI JSON文件路径 / Путь к файлу dois.json / '
                    f'Path to dois.json file (default: {CLIConfig.DEFAULT_PATHS["dois_file"]})'
                )
            )

            data_group.add_argument(
                '--crossref-authors',
                type=str,
                default=CLIConfig.DEFAULT_PATHS['crossref_authors'],
                metavar='PATH',
                help=(
                    'Crossref作者文件路径 / Путь к crossref_authors.json / '
                    f'Path to crossref_authors.json (default: {CLIConfig.DEFAULT_PATHS["crossref_authors"]})'
                )
            )

            data_group.add_argument(
                '--crossref-articles',
                type=str,
                default=CLIConfig.DEFAULT_PATHS['crossref_articles'],
                metavar='PATH',
                help=(
                    'Crossref文章文件路径 / Путь к crossref.json / '
                    f'Path to crossref.json (default: {CLIConfig.DEFAULT_PATHS["crossref_articles"]})'
                )
            )

        # 输出文件参数 / Параметры выходных файлов
        if add_output_files:
            output_group = parser.add_argument_group(
                'Выходные данные / Output Data',
                'Параметры для указания путей к результатам'
            )

            output_group.add_argument(
                '--output',
                '-o',
                type=str,
                default=CLIConfig.DEFAULT_PATHS['output'],
                metavar='PATH',
                help=(
                    '结果输出文件 / Путь к выходному файлу / '
                    f'Output file path (default: {CLIConfig.DEFAULT_PATHS["output"]})'
                )
            )

            output_group.add_argument(
                '--report',
                '-r',
                type=str,
                default=CLIConfig.DEFAULT_PATHS['report'],
                metavar='PATH',
                help=(
                    '测试报告文件 / Путь к отчету / '
                    f'Test report file path (default: {CLIConfig.DEFAULT_PATHS["report"]})'
                )
            )

        # 配置参数 / Параметры конфигурации
        if add_config:
            config_group = parser.add_argument_group(
                'Конфигурация / Configuration',
                'Параметры настройки системы'
            )

            config_group.add_argument(
                '--threshold',
                '-t',
                type=float,
                default=0.85,
                metavar='FLOAT',
                help=(
                    '相似度阈值 [0.0-1.0] / Порог сходства / '
                    'Similarity threshold for author merging (default: 0.85)'
                )
            )

            config_group.add_argument(
                '--language',
                '-l',
                type=str,
                choices=['zh', 'ru', 'en'],
                default='ru',
                help=(
                    '输出语言 / Язык вывода / '
                    'Output language (default: ru)'
                )
            )

            config_group.add_argument(
                '--limit',
                type=int,
                default=None,
                metavar='N',
                help=(
                    '处理记录数限制 / Лимит записей / '
                    'Limit number of records to process (default: no limit)'
                )
            )

            config_group.add_argument(
                '--max-workers',
                type=int,
                default=5,
                metavar='N',
                help=(
                    '最大并发工作线程数 / Максимум потоков / '
                    'Maximum number of worker threads (default: 5)'
                )
            )

        # 通用参数 / Общие параметры
        parser.add_argument(
            '--verbose',
            '-v',
            action='store_true',
            help='详细输出 / Подробный вывод / Verbose output'
        )

        parser.add_argument(
            '--debug',
            action='store_true',
            help='调试模式 / Режим отладки / Debug mode'
        )

        parser.add_argument(
            '--version',
            action='version',
            version='%(prog)s 2.0 (Incremental Author Disambiguation System)'
        )

        return parser

    @staticmethod
    def _get_usage_examples() -> str:
        """
        获取使用示例 / Получение примеров использования

        返回 / Возвращает / Returns:
            使用示例文本 / Текст с примерами
        """
        return '''
示例用法 / Примеры использования / Usage Examples:

  # 使用默认数据 / Использование данных по умолчанию / Use default data
  python script.py

  # 指定authors.json路径 / Указание пути к authors.json / Specify authors file
  python script.py --authors-file "C:/path/to/authors.json"

  # 指定dois.json路径 / Указание пути к dois.json / Specify DOIs file
  python script.py --dois-file "C:/path/to/dois.json"

  # 同时指定多个文件 / Указание нескольких файлов / Specify multiple files
  python script.py \\
      --authors-file "C:/path/to/authors.json" \\
      --dois-file "C:/path/to/dois.json" \\
      --output "results.json" \\
      --threshold 0.90

  # 详细输出模式 / Подробный вывод / Verbose mode
  python script.py --verbose --language ru

  # 限制处理数量 / Ограничение количества / Limit processing
  python script.py --limit 100 --max-workers 10

  # 调试模式 / Режим отладки / Debug mode
  python script.py --debug --verbose
        '''

    @staticmethod
    def validate_args(args: argparse.Namespace) -> bool:
        """
        验证参数有效性 / Валидация аргументов

        参数 / Параметры / Parameters:
            args: 解析后的参数 / Разобранные аргументы / Parsed arguments

        返回 / Возвращает / Returns:
            True如果有效 / True если валидны / True if valid

        抛出 / Исключения / Raises:
            ValueError: 参数无效时 / При невалидных аргументах / On invalid arguments
        """
        # 检查阈值范围 / Проверка порога / Check threshold range
        if hasattr(args, 'threshold'):
            if not 0.0 <= args.threshold <= 1.0:
                raise ValueError(
                    f"相似度阈值必须在 [0.0, 1.0] 范围内 / "
                    f"Порог сходства должен быть в диапазоне [0.0, 1.0] / "
                    f"Threshold must be in range [0.0, 1.0], got {args.threshold}"
                )

        # 检查文件存在性 / Проверка существования файлов / Check file existence
        file_attrs = ['authors_file', 'dois_file', 'crossref_authors', 'crossref_articles']

        for attr in file_attrs:
            if hasattr(args, attr):
                file_path = getattr(args, attr)
                if file_path and not Path(file_path).exists():
                    # 警告：文件不存在（允许继续，可能是输出文件）
                    # Предупреждение: файл не существует
                    print(
                        f"[WARNING / ПРЕДУПРЕЖДЕНИЕ] "
                        f"文件不存在 / Файл не существует / File not found: {file_path}"
                    )

        # 检查限制参数 / Проверка лимита / Check limit
        if hasattr(args, 'limit') and args.limit is not None:
            if args.limit <= 0:
                raise ValueError(
                    f"限制数量必须大于0 / "
                    f"Лимит должен быть > 0 / "
                    f"Limit must be > 0, got {args.limit}"
                )

        # 检查工作线程数 / Проверка количества потоков / Check max workers
        if hasattr(args, 'max_workers'):
            if args.max_workers <= 0:
                raise ValueError(
                    f"工作线程数必须大于0 / "
                    f"Количество потоков должно быть > 0 / "
                    f"Max workers must be > 0, got {args.max_workers}"
                )

        return True

    @staticmethod
    def print_config(args: argparse.Namespace) -> None:
        """
        打印配置信息 / Вывод конфигурации

        参数 / Параметры / Parameters:
            args: 解析后的参数 / Разобранные аргументы / Parsed arguments
        """
        print("=" * 80)
        print("配置信息 / Конфигурация / Configuration")
        print("=" * 80)

        # 打印所有参数 / Вывод всех аргументов / Print all arguments
        for key, value in vars(args).items():
            # 格式化键名 / Форматирование ключа / Format key name
            display_key = key.replace('_', ' ').title()
            print(f"  {display_key:25s}: {value}")

        print("=" * 80)


# 使用示例 / Пример использования / Usage Example
if __name__ == '__main__':
    # 创建解析器 / Создание парсера / Create parser
    parser = CLIConfig.create_base_parser(
        description='增量作者消歧系统测试 / Тест системы дезамбигуации авторов'
    )

    # 解析参数 / Парсинг аргументов / Parse arguments
    args = parser.parse_args()

    # 验证参数 / Валидация / Validate
    try:
        CLIConfig.validate_args(args)
    except ValueError as e:
        print(f"[ERROR / ОШИБКА] {e}")
        exit(1)

    # 打印配置 / Вывод конфигурации / Print config
    if args.verbose:
        CLIConfig.print_config(args)

    # 显示参数 / Показать аргументы / Show arguments
    print("\n解析的参数 / Разобранные аргументы / Parsed Arguments:")
    for key, value in vars(args).items():
        print(f"  {key}: {value}")
