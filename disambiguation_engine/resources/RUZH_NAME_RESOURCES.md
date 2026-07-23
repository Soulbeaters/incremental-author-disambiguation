# RuZh name-resource attribution and limits

These files provide type-level evidence for the Project Two conditional
Russian/Chinese author-disambiguation expert.  They contain no person records,
identity labels, publications or service predictions.

## Chinese surname aliases

`project1_chinese_surname_aliases.tsv` is deterministically derived from the
MIT-licensed Project One repository at `C:\program 1 in 2025`.  It contains:

- 462 Han surname aliases;
- 353 Pinyin aliases;
- 348 Palladius aliases for Chinese surnames written in Russian; and
- 41 Cantonese, Wade--Giles or other romanization variants.

The historical Project One module named `surname_russian_db.py` is not a
Russian-family-name database.  It maps Chinese surnames to Russian Palladius
spellings.  It is used only for Chinese cross-script evidence.

The exact Project One input hashes, output hash and MIT licence hash are in
`ruzh_name_resources.manifest.json`.

## Russian name-role lemmas

`opencorpora_russian_name_lemmas.tsv` contains nominative lemma evidence tagged
as surname (`Surn`), given name (`Name`) or patronymic (`Patr`) in OpenCorpora.
It was extracted from:

- `pymorphy3-dicts-ru==2.4.417150.4580142`;
- OpenCorpora dictionary format 0.92, source revision 417150; and
- corpus revision 4580142.

The derived data remain under **CC BY-SA 3.0**.  The builder code and the rest
of Project Two retain their own repository licence.  Source and download
documentation:

- <https://opencorpora.org/?page=downloads>
- <https://opencorpora.org/?page=export>
- <https://pypi.org/project/pymorphy3/>
- <https://github.com/no-plagiarism/pymorphy3-dicts>

Wheel and generated-file SHA-256 values are recorded in
`ruzh_name_resources.manifest.json`.

## Scientific boundary

Membership means only that a token has type-level name evidence in these
resources.  It does not prove nationality, ethnicity, language, or identity.
The runtime may use membership, ambiguity, morphology and cross-script
compatibility as model features or veto signals.  It must never merge two
authors solely because a dictionary entry or transliteration matches.

Rebuild:

```powershell
$env:PYTHONPATH = 'path\to\builder-only\pymorphy3-packages'
python scripts\build_ruzh_name_resources.py `
  --project1-root 'C:\program 1 in 2025' `
  --output-root 'disambiguation_engine\resources' `
  --pymorphy-wheel 'path\to\pymorphy3-2.0.6-py3-none-any.whl' `
  --dictionary-wheel 'path\to\pymorphy3_dicts_ru-2.4.417150.4580142-py2.py3-none-any.whl'
```
