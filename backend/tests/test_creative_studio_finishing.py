import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.services.creative_studio_picture import compile_picture_prompt, media_dimensions, compose_campaign_graphics
from app.services.creative_studio_video_finishing import (
    extract_overlay_events,
    extract_voiceover_events,
    normalize_voiceover_windows,
)
from app.services.ffmpeg_util import require_ffmpeg, probe_video_duration

BRIEF = 'Create a 15-second, 16:9 premium cinematic lifestyle advertisement for During Days, using the attached chair photograph as the authoritative product reference. Target 1080p, 24fps, with natural motion blur and the visual restraint of a professionally photographed furniture commercial.\nCampaign idea: “Make room for good days.”\nTell a compact, emotionally engaging story: a considered purchase becomes part of everyday home life. Progress through unboxing, product detail, family breakfast, a quiet personal moment and evening conversation. Finish with a beautiful product composition, synchronised voiceover and a clear shopping invitation.\nThe chair must remain the visual subject. Human moments should demonstrate its place in the home while keeping its silhouette, seating surface and construction visible.\nProduct identity — preserve throughout\nReproduce the chair shown in the attached reference:\nFour tall, outward-splayed legs with warm brown wood-grain surfaces.\nA gently shaped black upholstered seat with a slim, exposed wooden edge.\nA curved, horizontally proportioned backrest with black upholstery on its front and visible brown wood grain on its rear.\nThe same black rear mounting hardware and angled backrest supports.\nBlack metal footrest rails connecting the legs in the same arrangement as the photograph.\nThe same proportions, joinery, surface finish and relationship between seat, backrest and legs.\nShow two matching chairs in the lifestyle scenes, as in the reference. Their presence is a styling choice, not a claim that the product is sold as a pair.\nMaintain plausible counter height and comfortable-looking spatial clearance based on the reference. Keep all four feet grounded. Do not add armrests, wheels, a pedestal, a swivel mechanism or different upholstery. Do not describe the product as genuine leather, solid walnut, ergonomic or weight-rated without supplied specifications.\nCast and performance\nUse one consistent family:\nMother, approximately 35–40, shoulder-length dark hair, oatmeal cotton blouse and relaxed charcoal trousers.\nFather, approximately 35–40, short dark hair, muted olive overshirt and neutral trousers.\nTeenage daughter, approximately 15–17, simple dusty-blue top.\nPreserve their faces, hair, clothing and proportions across all appearances. Direct small, believable gestures: an exchanged glance, a plate passed naturally, a relaxed smile following a shared remark. Expressions should feel observed rather than performed for an advertisement.\nAdults use the chairs. The daughter joins the breakfast moment from the preparation side of the island. No climbing, rocking, exaggerated leaning or standing on the seats.\nThe voiceover is an off-camera narrator. The family must not lip-sync or appear to speak the narration.\nLocation and art direction\nOne thoughtfully styled contemporary Australian home, visually related to the reference photograph:\nWarm timber flooring, an ivory kitchen island, pale timber countertop, off-white walls, sheer curtains, simple ceramics and restrained greenery. Leave sufficient space around both chairs so their legs and footrests remain readable.\nUse a lived-in setting with a few intentional objects: a fruit bowl, two mugs, breakfast plates, a small book and a tablet. Avoid clutter and unrelated prominent appliances.\nMaintain the same architecture, counter, chair placement and window direction. Morning, afternoon and evening are separate moments connected through editing; lighting must remain stable within each shot.\n0.0–2.0 seconds — The arrival\nBegin close enough to feel tactile: a three-quarter overhead view of a substantial brown corrugated delivery carton on the kitchen floor beside the island.\nThe father’s hands open the already-loosened upper flaps and gently peel back protective paper, revealing the chair’s distinctive curved backrest. Frame the reveal so its wood-grain exterior and black upholstery immediately connect to the reference.\nUse tasteful “During Days” branding on the carton. Treat the packaging as art-directed concept packaging unless an actual packaging reference is supplied.\nShow convincing cardboard thickness, paper folds, contact shadows and hand pressure. Do not show a fully assembled chair magically emerging from an undersized box. Leave unpacking and any assembly outside the edit.\nCamera: approximately 50mm equivalent, a restrained downward move, shallow but usable depth of field.\nSound: soft cardboard flex, paper movement and the opening notes of the music.\nOn-screen text appears at 0.3 seconds:\n“Unbox a new favourite.”\nVoiceover begins at 0.4 seconds:\n“Unbox a new favourite.”\nDeliver with quiet anticipation and a slight smile. Let the narration continue naturally across the following cut, finishing by 2.4 seconds.\nTransition: Match the curve of the revealed backrest to the same curve on the unpacked chair in the next shot.\n2.0–3.5 seconds — The design reveal\nA low, three-quarter beauty shot of the fully unpacked chair beside the island. Make a short, controlled lateral move that reveals the black seat, exposed wooden edge, rear support and splayed legs.\nLet a soft band of window light trace the wood grain. Keep the black upholstery rich and textured rather than glossy. Show realistic contact shadows beneath the feet and gentle highlights on the metal footrest.\nUse approximately 65–85mm equivalent with enough depth of field to preserve the product’s recognisable shape. Avoid an extreme macro that makes the object unreadable.\nThe unpacking-to-finished-chair cut represents elapsed time.\nKeep “Unbox a new favourite.” visible until 3.2 seconds, then fade it out. After the opening voiceover finishes, leave a brief pause for the music and tactile product imagery.\nTransition: Cut on the father’s hand reaching toward the backrest to his hand resting in the same position during breakfast.\n3.5–6.5 seconds — Family breakfast\nMedium-wide, three-quarter kitchen view. Both parents are already seated naturally on the matching chairs. Their daughter slides a small plate of fruit across the countertop from the opposite side.\nThe mother receives the plate; the father exchanges a brief amused glance with their daughter. Capture one small family interaction, not several competing actions.\nKeep the camera on the dining side of the island so the chairs’ rear wood panels, black supports, seats and legs remain visible. One parent may be slightly angled, but neither should obscure the other chair completely.\nShow believable seated posture, feet resting naturally and slight cushion compression. Hands contact the plate correctly; it stays flat on the countertop.\nCamera: approximately 35mm equivalent, slow push forward of only a few centimetres. Compose at a natural seated eye level.\nLight: soft morning daylight, gentle curtain shadows, warm but neutral skin tones.\nSound: a quiet plate slide, ceramic contact and a hint of natural family laughter beneath the music. No intelligible character dialogue.\nOn-screen text appears at 3.8 seconds:\n“For everyday moments.”\nVoiceover, 3.9–5.6 seconds:\n“For everyday moments.”\nUse a warm, affectionate tone. Keep the delivery relaxed and the family’s reaction understated.\nTransition: Match-cut the mother’s hand closing around her breakfast mug to the same hand holding a mug during her quiet afternoon pause.\n6.5–8.5 seconds — A moment for herself\nThe same mother sits on the same chair, now enjoying a short break at the island. An open book lies beside her mug; a tablet rests unobtrusively nearby.\nBegin with the chair’s curved back and seat visible in the foreground, then make a subtle focus adjustment toward her relaxed profile. She glances down at the book and takes one small sip.\nThis scene communicates the chair’s role in reading, casual browsing and a personal pause. Do not introduce a complicated working sequence or a legible simulated interface.\nUse a 50mm-equivalent lens, natural skin texture and gentle afternoon light. Preserve the room and product geometry exactly.\nKeep “For everyday moments.” on screen until 8.3 seconds, allowing the message to connect the shared breakfast and personal pause.\nNo additional narration during this scene. Let the imagery breathe, with soft music and a subtle ceramic sound.\nTransition: A clean match cut on the mug returning to the counter carries us into the evening. Let the audio bridge the cut.\n8.5–11.5 seconds — Stay a little longer\nReturn to both parents seated at the same island in early evening. The kitchen now has soft amber practical lighting balanced with remaining cool window light.\nThe father sets down a mug as the mother reacts to a quiet remark with a small, spontaneous smile. They remain comfortably engaged with each other rather than addressing the camera.\nFrame both chairs clearly in a medium-wide composition. A slight lateral camera movement reveals the warm rear wood surfaces and black footrests without circling the subjects.\nKeep the room welcoming and attainable. No dramatic theatrical lighting, candle-filled set or exaggerated luxury styling.\nSound: a gentle ceramic tap and restrained laughter. Let the music open slightly here to support the emotional payoff, while remaining beneath the narration.\nOn-screen text, 8.7–11.2 seconds:\n“Stay a little longer.”\nVoiceover, 8.8–10.8 seconds:\n“Stay a little longer.”\nSoften the delivery to complement the evening conversation. Give “longer” a natural, gentle finish without stretching it theatrically.\nTransition: Match the position of the nearest chair into the final product composition. The final setup is a separate styled shot; people must not dissolve or disappear within a continuous take.\n11.5–15.0 seconds — Product and brand finish\nA carefully composed hero shot of both empty chairs beside the island, echoing the attached reference.\nPlace one chair at a front three-quarter angle to show the black seat and upholstered back. Position the second at a rear three-quarter angle to reveal the curved wood-grain back and black mounting hardware.\nShow complete legs, grounded feet and clear footrest geometry. Keep the island secondary. Use warm directional light, soft shadows and generous negative space above and to the right.\nMake a minimal push toward the pair, then settle into a stable final frame. The end card must remain fully readable for at least 2.5 seconds.\nReveal the complete end card at 12.0 seconds:\nDuring Days\nMake room for good days.\nShop Now\nduringdays.com.au\nUse the supplied official logo unchanged if available. Otherwise use a clean, accurately spelled text wordmark.\nVoiceover, 12.0–15.0 seconds:\n“During Days. Make room for good days.”\nClearly pronounce the brand, pause briefly, then deliver the closing line with calm confidence. Finish naturally before the video ends.\n“Shop Now” and the website remain visual-only, giving the closing narration room to breathe.\nOn-screen copy and graphic direction\nUse only these exact text moments:\n0.3–3.2 seconds: “Unbox a new favourite.”\n3.8–8.3 seconds: “For everyday moments.”\n8.7–11.2 seconds: “Stay a little longer.”\n12.0–15.0 seconds: The final brand, campaign line, CTA and website.\nUse a restrained editorial treatment: medium-weight modern sans-serif typography, charcoal on light backgrounds or warm white on darker backgrounds. Apply a subtle backing panel only when needed for readability. Reserve orange for the final CTA.\nKeep overlays fixed to the screen, within an 8% safe margin and away from faces, hands and important product details. Use brief, smooth fades; no bouncing words, animated letter effects or excessive graphic decoration.\nPreserve exact spelling, punctuation and brand naming. Text must remain stable, crisp and readable throughout its allotted duration.\nComposite the lettering after footage generation when possible. If the model cannot render exact typography, preserve clean negative space and add the text during finishing.\nVoiceover performance and synchronisation\nUse one warm, confident adult female voice with a natural Australian accent throughout. Delivery should feel intimate, polished and conversational, with gentle expression and clear pronunciation.\nAvoid exaggerated sales enthusiasm, robotic pacing, a theatrical announcer voice or excessive breathiness.\nSpeak only these exact lines:\n“Unbox a new favourite.”\n“For everyday moments.”\n“Stay a little longer.”\n“During Days. Make room for good days.”\nStart each spoken line after, or as, its matching text appears. Finish before that text disappears. Do not add words, paraphrase the copy, read production instructions or announce the website.\nKeep the narrator’s tone, accent, microphone character and perceived distance consistent across every line. The family must not lip-sync or appear to speak these words.\nIf a line overruns, adjust the performance within its allotted window rather than mechanically speeding up the voice. Do not truncate words, clip the final syllable or extend the film beyond 15 seconds.\nCamera, lighting and finishing\nMaintain a coherent lens language: medium-wide lenses for relationships, longer lenses for tactile product details. Use controlled dolly moves and deliberate cuts. Avoid drone-like movement, rapid orbits, whip pans and artificial zooms.\nProtect detail in the black upholstery and highlights in the pale kitchen. Preserve natural wood variation, subtle surface texture, realistic skin and physically plausible reflections.\nApply a gentle warm-neutral grade with restrained contrast and fine grain. Avoid excessive sharpening, artificial skin smoothing, heavy bloom and exaggerated shallow focus.\nThe intended look is refined live-action furniture advertising, with enough visual clarity to recognise the actual chair in every scene.\nMusic and sound mix\nUse an understated instrumental track with soft percussion, warm piano and light plucked textures. Build gently from the package reveal toward the family scenes, then resolve cleanly on the end card.\nIntegrate paper rustle, ceramics, subtle room tone and quiet laughter. Sound should give the objects weight and the home a sense of life.\nKeep the voiceover centred, clear and consistent. Gently lower music and environmental sounds beneath each spoken line, restoring them smoothly during pauses.\nAvoid abrupt volume changes, heavy reverb, overpowering percussion and clipped endings. Preserve quiet moments between lines rather than filling every second with narration.\nGeneration workflow and final checks\nCreate consistent reference frames for the product’s front, rear and side views using only details supported by the supplied image. Establish the family, kitchen and lighting before generating motion.\nWhere supported, generate the six shots separately using shared references, then edit them to the exact 15-second timeline. Prioritise product consistency and believable movement over elaborate transitions.\nRecord the voiceover to the specified timings, synchronise it with the text overlays, and complete the music and effects mix after the picture edit is locked.\nReject results with changing chair proportions, missing legs, altered back supports, duplicated footrests, floating feet, intersecting bodies, unstable hands, sliding seated figures, shifting wood grain or flickering upholstery.\nReject misspelled text, drifting graphics, narration that differs from the visible message, inconsistent voices, character lip-sync to the narrator or a rushed closing line.\nDo not add invented prices, discounts, comfort guarantees, material claims, delivery promises or customer endorsements.\nThe finished advertisement should make the viewer imagine this chair in their own daily life: a distinctive object, quietly present in the moments that make a home.'

class FinishingTests(unittest.IsolatedAsyncioTestCase):
    def test_sectioned_timed_scenes_extract_copy_without_separator_lines(self):
        brief = (
            "SCENE 1 - OPEN | 0-4 SECONDS\nVISUAL DIRECTION:\nA natural action.\n"
            "ON-SCREEN TEXT:\n\u201cStart here\u201d\n----------------\n"
            "SCENE 2 - QUIET | 4-8 SECONDS\nVISUAL DIRECTION:\nContinue.\n"
            "ON-SCREEN TEXT:\nNo additional text.\nLet the image breathe.\n----------------\n"
            "SCENE 3 - END | 8-12 SECONDS\nVISUAL DIRECTION:\nFinish.\n"
            "FINAL ON-SCREEN TEXT:\nACME\nShop Today\n----------------"
        )
        self.assertEqual(
            extract_overlay_events(brief),
            [(0.0, 4.0, "Start here"), (8.0, 12.0, r"ACME\NShop Today")],
        )

    def test_picture_has_every_scene_but_no_editorial_copy(self):
        picture = compile_picture_prompt(BRIEF, duration=15)
        for title in ['The arrival', 'The design reveal', 'Family breakfast', 'A moment for herself', 'Stay a little longer', 'Product and brand finish']:
            self.assertIn(title, picture)
        for text in ['Unbox a new favourite.', 'For everyday moments.', 'duringdays.com.au', 'Shop Now', '0.3', '3.8', '8.7', '12.0–15.0 seconds:']:
            self.assertNotIn(text, picture)
        self.assertIn('black rear mounting hardware', picture)
        self.assertIn('Both parents are already seated', picture)
        self.assertIn('BRAND-SURFACE LOCK:', picture)
        self.assertIn('plain in that frame must remain completely plain', picture)

    def test_exact_narration_and_website_stay_in_finishing(self):
        self.assertEqual(len(extract_voiceover_events(BRIEF)), 4)
        events=extract_overlay_events(BRIEF)
        self.assertEqual(len(events), 4)
        self.assertEqual(events[-1], (12.0,15.0,r'During Days\NMake room for good days.\NShop Now\Nduringdays.com.au'))

    def test_tight_dialogue_windows_are_auto_expanded(self):
        events = [(0.2, 1.9, "Okay, my ugly old kettle is officially retired.")]
        normalized = normalize_voiceover_windows(events, duration_seconds=15)
        self.assertEqual(len(normalized), 1)
        start, end, text = normalized[0]
        self.assertEqual(text, events[0][2])
        self.assertGreaterEqual(end - start, len(text.split()) * 0.42)

    async def test_seedance_speech_failure_still_generates_video(self):
        from app.services.creative_studio_job_service import create_job, run_creative_studio_job, get_job
        provider = Mock()
        provider.generate = AsyncMock(return_value={
            "status": "done", "url": "fixture.mp4", "provider": "byteplus",
            "model": "ark-seedance-2-0", "duration_seconds": 15,
        })
        job = await create_job(tenant_id='test', payload={
            'media_mode': 'video', 'model': 'ark-seedance-2-0',
            'prompt': BRIEF, 'source_brief': BRIEF, 'duration_seconds': 15, 'sound_on': True,
        })
        with (
            patch('app.services.file_service.file_service.assert_writable'),
            patch('app.services.creative_studio_speech.prepare_narration', AsyncMock(side_effect=RuntimeError('Speech account has no credits'))),
            patch('app.services.media.registry.get_video_provider', return_value=provider),
            patch('app.services.creative_studio_picture.compose_campaign_graphics', return_value=('fixture.mp4', False)),
            patch('app.services.video_subtitles._ensure_local_video', return_value=Path(__file__)),
            patch('app.services.ffmpeg_util.probe_has_audio', return_value=True),
        ):
            await run_creative_studio_job(job)
        result = await get_job(job)
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertFalse(result.get('audio_warning'))
        self.assertEqual((result.get('voiceover') or {}).get('status'), 'native')
        provider.generate.assert_awaited()

    async def test_prepared_narration_disables_per_clip_seedance_speech(self):
        from app.services.creative_studio_job_service import create_job, run_creative_studio_job
        events = extract_voiceover_events(BRIEF)
        prepared = {
            "provider": "openai", "voice": "marin",
            "lines": [
                {"start": a, "end": b, "text": text, "path": "prepared.wav", "duration": b - a}
                for a, b, text in events
            ],
        }
        provider = Mock()
        provider.generate = AsyncMock(return_value={
            "status": "done", "url": "fixture.mp4", "provider": "byteplus",
            "model": "ark-seedance-2-0", "duration_seconds": 15,
        })
        job = await create_job(tenant_id="test", payload={
            "media_mode": "video", "model": "ark-seedance-2-0",
            "prompt": BRIEF, "source_brief": BRIEF, "duration_seconds": 15, "sound_on": True,
        })
        with (
            patch("app.services.file_service.file_service.assert_writable"),
            patch("app.services.creative_studio_speech.prepare_narration", AsyncMock(return_value=prepared)),
            patch("app.services.media.registry.get_video_provider", return_value=provider),
            patch("app.services.creative_studio_video_finishing.apply_timed_voiceover", AsyncMock(
                return_value=("fixture.mp4", {"status": "done", "voice": "marin"})
            )),
            patch("app.services.creative_studio_picture.compose_campaign_graphics", return_value=("fixture.mp4", False)),
            patch("app.services.video_subtitles._ensure_local_video", return_value=Path(__file__)),
            patch("app.services.ffmpeg_util.probe_has_audio", return_value=True),
        ):
            await run_creative_studio_job(job)
        request = provider.generate.call_args.kwargs
        self.assertTrue(request["brief"]["skip_voiceover"])
        self.assertIn("NO speech, dialogue or narration", request["prompt"])

    def test_actual_landscape_dimensions_and_exact_graphics(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);source=work/'source.mp4';output=work/'graphics-fixture.mp4'
            subprocess.run([require_ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=c=gray:s=1920x1080:r=24','-t','15','-c:v','libx264','-preset','ultrafast',str(source)],capture_output=True,check=True)
            self.assertEqual(media_dimensions(source),(1920,1080))
            def save(content,*args):
                output.write_bytes(content);return {'file_url':str(output)}
            logo=work/'logo.png'
            from PIL import Image
            Image.new('RGBA',(180,50),'orange').save(logo)
            with patch('app.services.creative_studio_picture._ensure_local_video',return_value=source),patch('app.services.creative_studio_picture.file_url_to_local_path',return_value=logo),patch('app.services.creative_studio_picture.file_service.save_bytes',side_effect=save):
                url,done=compose_campaign_graphics('fixture',extract_overlay_events(BRIEF),tenant_id='test',logo_url='logo')
            self.assertTrue(done)
            self.assertAlmostEqual(probe_video_duration(output),15,delta=0.1)
            subprocess.run([require_ffmpeg(),'-v','error','-y','-ss','13','-i',str(output),'-frames:v','1',str(work/'graphics-fixture.png')],capture_output=True,check=True)

if __name__=='__main__':
    unittest.main()
