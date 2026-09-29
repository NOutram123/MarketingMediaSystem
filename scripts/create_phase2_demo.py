"""Create/reuse a non-commercial Phase 2 fixture without paid API calls."""
import json

from backend.config import Settings
from backend.schemas import BrandKit, CampaignPlan, ShotPlan
from backend.store import Store


def main():
    settings = Settings()
    store = Store(settings.data_dir)
    marker = settings.data_dir / 'benchmarks/phase2_demo_project.json'
    if marker.is_file():
        project_id = json.loads(marker.read_text(encoding='utf-8'))['project_id']
        print(json.dumps({'project_id': project_id, 'reused': True}))
        return
    shots = [
        ShotPlan(purpose='Introduce the product', visual='Sunlit berry drink bottle on a kitchen table',
                 camera='slow push in', duration_seconds=3, narration='Meet your bright berry moment.',
                 image_prompt='Cinematic commercial storyboard image, a clear glass bottle filled with ruby berry drink on a sunlit wooden kitchen table, fresh berries beside it, warm natural light, consistent simple bottle shape, no text, no logo',
                 video_prompt='A clear glass bottle of ruby berry drink stands on a wooden kitchen table. Soft morning light shifts as the camera slowly pushes toward the bottle. Natural gentle motion, no text, no logo.'),
        ShotPlan(purpose='Show the ingredients', visual='Fresh berries and condensation beside the bottle',
                 camera='macro slide', duration_seconds=3, narration='Fresh berry flavour shines through.',
                 image_prompt='Cinematic macro product storyboard image, ruby berry drink in a clear glass bottle beside fresh raspberries and blueberries, droplets on glass, warm kitchen light, consistent simple bottle shape, no text, no logo',
                 video_prompt='Macro view of fresh berries and cool condensation beside the same clear glass bottle of ruby berry drink. Camera slides gently across the table, realistic natural motion, no text, no logo.'),
        ShotPlan(purpose='Create a refreshing moment', visual='Berry drink poured into a glass',
                 camera='gentle close-up', duration_seconds=3, narration='A little colour in every sip.',
                 image_prompt='Cinematic product storyboard image, ruby berry drink pouring from a simple clear glass bottle into a drinking glass on a wooden table, soft daylight, berries nearby, no text, no logo',
                 video_prompt='Ruby berry drink pours slowly from a clear glass bottle into a drinking glass. Soft daylight glints on the liquid; camera holds a gentle close-up, no text, no logo.'),
        ShotPlan(purpose='Show everyday enjoyment', visual='Drink on a picnic table in soft afternoon light',
                 camera='wide reveal', duration_seconds=3, narration='Made for easy everyday moments.',
                 image_prompt='Cinematic lifestyle storyboard image, the same simple clear glass bottle of ruby berry drink on a picnic table with fresh berries, warm afternoon garden light, shallow depth of field, no people, no text, no logo',
                 video_prompt='A simple clear glass bottle of ruby berry drink rests on a picnic table in warm afternoon light. Leaves move gently in the breeze as the camera reveals the setting, no text, no logo.'),
        ShotPlan(purpose='End on a product hero', visual='Bottle and glass on neutral tabletop',
                 camera='slow hero push', duration_seconds=3, narration='SpiceBerry. Bring a brighter moment.',
                 image_prompt='Cinematic clean product hero storyboard image, a simple clear glass bottle of ruby berry drink beside a filled glass and fresh berries on a neutral tabletop, luminous soft light, centered composition, no text, no logo',
                 video_prompt='A simple clear glass bottle of ruby berry drink and filled glass stand beside fresh berries on a neutral tabletop. Camera slowly pushes in for a clean product hero finish, no text, no logo.'),
    ]
    plan = CampaignPlan(concept='Bright berry moments', target_audience='Adults',
                        key_message='A colourful berry-flavoured drink for everyday moments',
                        script='Meet your bright berry moment. Fresh berry flavour shines through. A little colour in every sip. Made for easy everyday moments. SpiceBerry. Bring a brighter moment.',
                        claims_used=['Berry flavour'], shots=shots)
    brand = BrandKit(product_name='SpiceBerry', description='Fictional berry-flavoured drink',
                     approved_claims=['Berry flavour'], visual_style='warm cinematic product photography')
    project = store.create_project('Phase 2 SpiceBerry local demo',
                                   'Create an approximately 15-second YouTube landscape advert for the fictional SpiceBerry drink. This is a non-commercial local pipeline demonstration.',
                                   brand.model_dump())
    project_id = project['id']
    store.review_gate(project_id, 'brief', True, 'Approved only for automated local pipeline demonstration')
    store.set_plan(project_id, plan.model_dump())
    store.review_gate(project_id, 'concept', True, 'Approved only for automated local pipeline demonstration')
    store.set_shots(project_id, [shot.model_dump() for shot in shots])
    store.review_gate(project_id, 'storyboard', True, 'Approved only for automated local pipeline demonstration')
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'project_id': project_id}, indent=2), encoding='utf-8')
    print(json.dumps({'project_id': project_id, 'reused': False}))


if __name__ == '__main__':
    main()
