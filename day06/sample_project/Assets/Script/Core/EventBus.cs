// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：EventBus.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：定义系统事件总线，负责协调唤醒、录音、播放等各类流程事件，适用于解耦模块通信。
// ─────────────────────────────────────────────────────────────────────────────


// VoiceSystem/Core/EventBus.cs
using System;

public static class EventBus
{
    // ────── 唤醒与语音采集事件 ──────

    public static event Action? OnWake;                            // 唤醒词触发
    public static event Action<byte[]>? OnSpeechCaptured;          // 录音完成，上传前
    public static event Action<bool>? OnSpeakerVerified;           // 声纹验证成功与否
    public static event Action<byte[], string>? OnTtsReady;        // TTS 成功，带音频+文本

    // ────── 文本处理事件 ──────

    public static event Action<string>? OnTextDelta;               // 实时字幕流

    // ────── 播放控制事件 ──────

    public static event Action? OnAudioPlayStart;                  // 播放开始
    public static event Action? OnAudioPlayEnd;                    // 播放结束

    // ────── 用户指令事件 ──────

    public static event Action? OnExit;                            // 用户说“停止”

    // ────── 通用触发方法 ──────

    public static void RaiseWake() => OnWake?.Invoke();
    public static void RaiseSpeechCaptured(byte[] _Wav) => OnSpeechCaptured?.Invoke(_Wav);
    public static void RaiseSpeakerVerified(bool _Ok) => OnSpeakerVerified?.Invoke(_Ok);
    public static void RaiseTtsReady(byte[] _Wav, string _Text) => OnTtsReady?.Invoke(_Wav, _Text);
    public static void RaiseTextDelta(string _Text) => OnTextDelta?.Invoke(_Text);
    public static void RaiseAudioPlayStart() => OnAudioPlayStart?.Invoke();
    public static void RaiseAudioPlayEnd() => OnAudioPlayEnd?.Invoke();
    public static void RaiseExit() => OnExit?.Invoke();
}
