[Document Homepage](./../README.md)
# Project Structure
```
project/
├── .github/
│   └── workflows/
│       └── process_submission.yml
├── backups/
├── config/
│   ├── categories_config.py
│   ├── config_default.ini
│   ├── config.ini
│   └── tag_config.py
├── docs/
├── figures/
├── scripts/
│   ├── update_submission_figures.py
│   ├── validate_submission.py
│   └── send_notification.py
├── src/
│   ├── core/
│   │   ├── config_loader.py
│   │   ├── database_manager.py
│   │   ├── database_model.py
│   │   └── update_file_utils.py
│   ├── ai_generator.py
│   ├── convert.py
│   ├── process_zotero_meta.py
│   ├── submit_gui.py
│   ├── submit_logic.py 
│   ├── update.py
│   ├── utils.py
│   └── validate.py
├── tests/
├── paper_database.xlsx
├── pyproject.toml
├── README.md
├── submit_template.json
├── submit_template.xlsx
├── submit.py
└── SurveyPaperSubmitGUI.exe
```
