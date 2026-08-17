// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：VoiceCapture.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：用于从麦克风捕获音频数据，并通过最大振幅判断静默，自动截取有效语音数据上传事件总线。
// ─────────────────────────────────────────────────────────────────────────────

// VoiceSystem/Runtime/VoiceCapture.cs
using UnityEngine;
using System.Collections;
using System.Linq;
using System.IO;

[AddComponentMenu("VoiceSystem/Runtime/Voice Capture")]
public sealed class VoiceCapture : MonoBehaviour
{
    [Header("录音与 VAD 配置")]

    // 采样率（Hz）
    [Header("音频采样率")]
    [SerializeField] int _SampleRate = 16000;

    // 触发静默判定的最大振幅阈值
    [Header("触发静默判定的最大振幅阈值")]
    [SerializeField] float _VadThreshold = 0.28f;

    // 静默判定时长（毫秒）
    [Header("静默判定时长")]
    [SerializeField] float _SilenceMs = 1200f;

    // 单段最长录音时长（秒）
    [Header("最长录音时长")]
    [SerializeField] float _MaxDuration = 30f;

    [Tooltip("是否允许本轮录音被提交（由外部控制）")]
    public bool _AllowCapture = true;

    AudioClip _Clip;
    bool _Capturing;
    float _SpeechEndTime;
    bool _HasSpeechDetected = false;

    void OnEnable() => EventBus.OnWake += BeginCapture;
    void OnDisable() => EventBus.OnWake -= BeginCapture;

    /// <summary>
    /// 开始麦克风录音并启动静默检测协程
    /// </summary>
    public void BeginCapture()
    {
        if (_Capturing) return;
        _Capturing = true;
        _HasSpeechDetected = false;

        _Clip = Microphone.Start(null, true, Mathf.CeilToInt(_MaxDuration), _SampleRate);
        _SpeechEndTime = Time.time;
        StartCoroutine(VadLoop());
        Debug.Log("[VoiceCapture] 已开始录音");
    }

    /// <summary>
    /// 停止录音并释放麦克风资源
    /// </summary>
    public void StopRecording()
    {
        if (!_Capturing) return;

        Debug.Log("[VoiceCapture] 强制停止录音");
        _Capturing = false;
        Microphone.End(null);
    }

    /// <summary>
    /// 基于振幅实现的静默检测主循环
    /// </summary>
    IEnumerator VadLoop()
    {
        float[] _Buf = new float[256];

        while (_Capturing)
        {
            int _Pos = Microphone.GetPosition(null);
            if (_Pos > _Buf.Length)
            {
                _Clip.GetData(_Buf, _Pos - _Buf.Length);
                if (_Buf.Any(s => Mathf.Abs(s) > _VadThreshold))
                {
                    _HasSpeechDetected = true;
                    _SpeechEndTime = Time.time;
                }
            }

            // 若静默时间超过阈值或录音超时，结束
            if (Time.time - _SpeechEndTime > _SilenceMs / 1000f ||
                Time.time - _SpeechEndTime > _MaxDuration)
            {
                FinalizeClip();
                yield break;
            }

            yield return null;
        }
    }

    /// <summary>
    /// 截取录音内容并触发上传事件
    /// </summary>
    void FinalizeClip()
    {
        _Capturing = false;
        int _Samples = Microphone.GetPosition(null);
        Microphone.End(null);

        if (!_AllowCapture)
        {
            Debug.Log("[VoiceCapture] 当前不允许捕获（播放中讲话），忽略");
            return;
        }

        if (!_HasSpeechDetected || _Samples <= 0)
        {
            Debug.LogWarning("[VoiceCapture] 无有效讲话，跳过本轮上传");
            return;
        }

        float[] _Data = new float[_Samples];
        _Clip.GetData(_Data, 0);

        AudioClip _Trimmed = AudioClip.Create("speech", _Samples, 1, _SampleRate, false);
        _Trimmed.SetData(_Data, 0);

        byte[] _Wav = WavUtility.FromAudioClip(_Trimmed);
        EventBus.RaiseSpeechCaptured(_Wav);
        Debug.Log($"[VoiceCapture] 录音完成 ({_Trimmed.length:F2}s)，已发送事件");

        //File.WriteAllBytes(Application.persistentDataPath + "/verify.wav", _Wav);
        //Debug.Log("🎙️ 已保存录音到：" + Application.persistentDataPath + "/verify.wav");

        // 启动 ASR 协程
        StartCoroutine(GetComponent<FastApiAsrClient>().UploadAndRecognize(_Wav, "speech.wav"));

        // 触发事件总线也保留
        EventBus.RaiseSpeechCaptured(_Wav);

    }
}
