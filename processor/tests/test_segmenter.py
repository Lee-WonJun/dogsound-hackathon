import unittest

from processor.segmenter import AudioSegmenter


class SegmenterTests(unittest.TestCase):
    def test_segmenter_emits_utterance_after_silence(self) -> None:
        segmenter = AudioSegmenter(
            sample_rate=1000,
            frame_ms=20,
            silence_ms=60,
            min_utterance_ms=60,
            start_threshold=0.05,
            stop_threshold=0.02,
        )
        sound_frame = [0.1] * 20
        silence_frame = [0.0] * 20
        emitted = []

        for frame in [silence_frame, sound_frame, sound_frame, sound_frame, silence_frame, silence_frame, silence_frame]:
            emitted.extend(segmenter.process_frame(frame))

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].frame_count, 3)
        self.assertEqual(emitted[0].duration_ms, 60)

    def test_segmenter_ignores_too_short_blips(self) -> None:
        segmenter = AudioSegmenter(
            sample_rate=1000,
            frame_ms=20,
            silence_ms=40,
            min_utterance_ms=100,
            start_threshold=0.05,
            stop_threshold=0.02,
        )
        sound_frame = [0.1] * 20
        silence_frame = [0.0] * 20
        emitted = []

        for frame in [sound_frame, silence_frame, silence_frame]:
            emitted.extend(segmenter.process_frame(frame))

        self.assertEqual(emitted, [])

    def test_segmenter_waits_for_silence_instead_of_auto_submitting(self) -> None:
        segmenter = AudioSegmenter(
            sample_rate=1000,
            frame_ms=20,
            silence_ms=60,
            min_utterance_ms=60,
            start_threshold=0.05,
            stop_threshold=0.02,
        )
        sound_frame = [0.1] * 20
        emitted = []

        for _ in range(20):
            emitted.extend(segmenter.process_frame(sound_frame))

        self.assertEqual(emitted, [])
        self.assertTrue(segmenter.is_recording)


if __name__ == "__main__":
    unittest.main()
