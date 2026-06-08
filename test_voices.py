"""Test which edge-tts voices work."""
import asyncio
import tempfile
import os

async def test_voice(voice_name):
    """Test if a voice works with edge-tts."""
    try:
        import edge_tts
        comm = edge_tts.Communicate("Hello, this is a test.", voice=voice_name)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(tmp_fd)
        try:
            await comm.save(tmp_path)
            size = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
            return True, size
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception as e:
        return False, str(e)

async def main():
    voices = [
        ("Brian", "en-US-BrianNeural"),
        ("Guy", "en-US-GuyNeural"),
        ("Tony HD", "en-US-TonyNeural"),
        ("Davis HD", "en-US-DavisNeural"),
        ("William AU", "en-AU-WilliamNeural"),
        ("Ava", "en-US-AvaNeural"),
        ("Emma", "en-US-EmmaNeural"),
        ("Jenny", "en-US-JennyNeural"),
        ("Aria HD", "en-US-AriaNeural"),
        ("Jane HD", "en-US-JaneNeural"),
        ("Sonia UK", "en-GB-SoniaNeural"),
    ]
    
    print("Testing edge-tts voices...\n")
    for name, voice_id in voices:
        success, result = await test_voice(voice_id)
        if success:
            print(f"✓ {name} ({voice_id}) - OK ({result} bytes)")
        else:
            print(f"✗ {name} ({voice_id}) - FAILED: {result}")

if __name__ == "__main__":
    asyncio.run(main())