// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：ISpeakerSvc.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：定义声纹识别服务接口，支持注册用户声纹和验证相似度，可对接本地或远程服务。
// ─────────────────────────────────────────────────────────────────────────────


// VoiceSystem/Core/ISpeakerSvc.cs
using System.Collections.Generic;
using System.Threading.Tasks;

public interface ISpeakerSvc
{
    /// <summary>
    /// 注册声纹信息
    /// </summary>
    /// <param name="_WavFiles">多个音频片段</param>
    /// <param name="_SpeakerId">说话人标识</param>
    /// <returns>是否注册成功</returns>
    Task<bool> RegisterAsync(IList<byte[]> _WavFiles, string _SpeakerId);

    /// <summary>
    /// 验证说话人与声纹匹配度
    /// </summary>
    /// <param name="_WavFile">待验证音频</param>
    /// <param name="_SpeakerId">说话人 ID</param>
    /// <returns>匹配得分（0 ~ 1）</returns>
    Task<float> VerifyAsync(byte[] _WavFile, string _SpeakerId);
}
