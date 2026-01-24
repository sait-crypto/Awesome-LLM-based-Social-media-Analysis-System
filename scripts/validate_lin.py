import sys, os
# ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.core.update_file_utils import UpdateFileUtils
from src.core.config_loader import get_config_instance

uf = UpdateFileUtils()
config = get_config_instance()
# specify the conflict JSON file
conflict_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'submit_template_冲突文件_LiXia_20260107152433.json')
raw = uf.read_json_file(conflict_file)
print('Loaded JSON type:', type(raw))
if isinstance(raw, dict) and 'papers' in raw:
    papers = raw['papers']
else:
    papers = raw if raw else []
for i,item in enumerate(papers):
    title=item.get('title','')
    pipe=item.get('pipeline_image','')
    print(i, title[:40], 'pipeline_image=', repr(pipe))
    from src.core.database_model import Paper
    tags = uf.config.get_non_system_tags()
    normalized = uf.normalize_json_papers([item], uf.config)
    pd = uf._dict_to_paper_data(normalized[0], tags)
    paper = Paper.from_dict(pd)
    valid, errors, _ = paper.validate_paper_fields(uf.config, check_required=False, check_non_empty=True)
    print('  valid=', valid, 'errors=', errors)
    print('  normalized pipeline_image in Paper.__post_init__:', paper.pipeline_image)
