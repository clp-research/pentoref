from moviepy.editor import AudioFileClip, VideoFileClip, concatenate


def create_video_clip(audio_source, video_source, start, end, target_filepath):
    """Creates a clip of the video between start and end at filepath"""
    if video_source is None:
        print "No video source"
        return
    if audio_source is None:
        print "No audio source"
        return
    audio1 = AudioFileClip(audio_source)
    video1 = VideoFileClip(video_source).set_audio(audio1)
    vclip = video1.subclip(start, end)
    vclip.write_videofile(target_filepath)
    return


def create_audio_clip(audio_source, start, end, target_filepath):
    """Creates a clip of the video between start and end (both in seconds)
    at filepath"""
    if audio_source is None:
        print "No audio source", audio_source
    audio1 = AudioFileClip(audio_source)
    aclip = audio1.subclip(start, end)
    aclip.write_audiofile(target_filepath)
    return
