// ────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：SpeakerSvcProxy.cs
// 作者：Maddie
// 日期：2025年04月23日
// ────────────────────────────────────────────────────────────────────────────
// 说明：用于代理声纹注册与验证逻辑，支持缓存多段注册语音、阈值比对验证，以及对接 Flask 服务。
// ────────────────────────────────────────────────────────────────────────────

// VoiceSystem/Runtime/SpeakerSvcProxy.cs
using UnityEngine;
using UnityEngine.Networking;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Net;

[AddComponentMenu("VoiceSystem/Runtime/Speaker Service Proxy")]
public sealed class SpeakerSvcProxy : MonoBehaviour, ISpeakerSvc
{
    [Header("Flask 后端")]
    [SerializeField] string _ServerBase = "http://172.16.10.18:5000";
    [SerializeField] string _SpeakerId = "Maddie";
    [Header("注册模式")]
    [SerializeField] bool _RegisterMode = false;          // Inspector 勾选进入注册
    [Header("验证阈值")]
    [SerializeField] float _VerifyThreshold = 0.4f;      // 0.4f 以上为通过

    List<byte[]> _Cache = new();
    const int REG_SEGMENTS = 3;


    void OnEnable() => EventBus.OnSpeechCaptured += HandleSpeech;
    void OnDisable() => EventBus.OnSpeechCaptured -= HandleSpeech;

    /// <summary>
    /// 异步初始化：等待配置加载并读取服务参数
    /// </summary>
    private async Task StartAsync()
    {

        // 1) 确保配置已加载
        //await ConfigService.InitAsync();
        while (!ConfigService._Loaded)
        {
            Debug.LogWarning("[SpeakerSvc] 等待配置初始化中...");
            await Task.Delay(100);
        }

        // 读取配置文件
        _ServerBase = ConfigService.Get("VocalPrint", "_ServerBaseUrl");
        _SpeakerId = ConfigService.Get("VocalPrint", "_SpeakerId");

        //print(_ServerBase);

        // 读取注册模式
        //_RegisterMode = ConfigService.Get("VocalPrint", "_RegisterMode") == "true";
    }

    /// <summary>
    /// 录音事件处理，根据是否注册模式调用注册或验证流程
    /// </summary>
    /// <param name="_Wav">录音的 PCM 数据</param>
    void HandleSpeech(byte[] _Wav)
    {
        if (_RegisterMode)
        {
            _Cache.Add(_Wav);
            Debug.Log($"[SpeakerSvc] 已缓存 {_Cache.Count}/3 段注册语音");

            if (_Cache.Count >= REG_SEGMENTS)
            {
                _SpeakerId = ConfigService.Get("VocalPrint", "_SpeakerId");
                _ = RegisterAsync(_Cache, _SpeakerId);       // 异步执行
            }
        }
        else
        {
            _SpeakerId = ConfigService.Get("VocalPrint", "_SpeakerId");
            _ = VerifyAsync(_Wav, _SpeakerId);               // 异步执行
        }
    }

    // ───────────────── ISpeakerSvc ─────────────────

    /// <summary>
    /// 外部调用：进入注册模式（如唤醒词“注册”）
    /// </summary>
    /// <summary>
    /// 外部调用：进入注册模式，清空缓存，等待录音
    /// </summary>
    public void EnterRegisterMode()
    {
        _RegisterMode = true;
        _Cache.Clear();
        Debug.Log("[SpeakerSvc] 进入注册模式，请说三段音频");
    }


    /// <summary>
    /// 向服务端提交声纹注册请求
    /// </summary>
    /// <param name="_Wavs">注册音频段列表</param>
    /// <param name="_Id">说话人标识</param>
    /// <returns>是否注册成功</returns>
    public async Task<bool> RegisterAsync(IList<byte[]> _Wavs, string _Id)
    {
        WWWForm _Form = new();

        _Form.AddField("speaker_id", _Id);
        foreach (var w in _Wavs)
            _Form.AddBinaryData("audio", w, "clip.wav", "audio/wav");

        using UnityWebRequest _Req = UnityWebRequest.Post($"{_ServerBase.TrimEnd('/')}/register", _Form);
        await _Req.SendWebRequest().AsTask();


        bool _OK = _Req.result == UnityWebRequest.Result.Success;
        Debug.Log($"[SpeakerSvc] 注册 {(_OK ? "成功" : "失败")}");

        if (_OK) _RegisterMode = false;          // 退出注册模式
        EventBus.RaiseSpeakerVerified(_OK);    // 注册结束也当作通过
        _Cache.Clear();
        return _OK;
    }

    /// <summary>
    /// 向服务端提交声纹验证请求，返回得分
    /// </summary>
    /// <param name="_Wav">音频数据</param>
    /// <param name="_Id">说话人 ID</param>
    /// <returns>匹配分数（0 ~ 1）</returns>
    public async Task<float> VerifyAsync(byte[] _Wav, string _Id)
    {
        WWWForm _Form = new();
        _Form.AddField("speaker_id", _Id);
        _Form.AddBinaryData("audio", _Wav, "clip.wav", "audio/wav");

        Debug.Log($"[Verify] 音频 Base64 长度: {System.Convert.ToBase64String(_Wav).Length}");


        using UnityWebRequest _Req = UnityWebRequest.Post($"{_ServerBase.TrimEnd('/')}/verify", _Form);
        await _Req.SendWebRequest().AsTask();


        float _Score = 0f;
        if (_Req.result == UnityWebRequest.Result.Success)
        {
            var _Json = JsonUtility.FromJson<VerifyRes>(_Req.downloadHandler.text);
            _Score = _Json.score;
        }

        bool _Pass = _Score > _VerifyThreshold;
        Debug.Log($"[SpeakerSvc] 验证 {(_Pass ? "通过" : "失败")} (_Score={_Score:F3})");
        EventBus.RaiseSpeakerVerified(_Pass);
        return _Score;
    }

    [System.Serializable] class VerifyRes { public float score; }
}