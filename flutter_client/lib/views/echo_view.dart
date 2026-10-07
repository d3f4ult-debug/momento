import 'package:flutter/material.dart';
import '../services/bridge_service.dart';
import '../theme/app_theme.dart';

class EchoView extends StatefulWidget {
  final BridgeService bridgeService;

  const EchoView({super.key, required this.bridgeService});

  @override
  State<EchoView> createState() => _EchoViewState();
}

class _EchoViewState extends State<EchoView> {
  final _ttsController = TextEditingController();
  String _selectedVoice = 'nova';
  bool _isProcessing = false;
  List<Map<String, dynamic>> _recordings = [];
  String? _statusMessage;
  String _liveTranscription = '';

  final List<String> _voices = ['nova', 'shimmer', 'echo', 'onyx', 'alloy'];

  @override
  void initState() {
    super.initState();
    _loadRecordings();
  }

  @override
  void dispose() {
    _ttsController.dispose();
    super.dispose();
  }

  Future<void> _loadRecordings() async {
    final items = await widget.bridgeService.getEchoRecordings();
    if (mounted) {
      setState(() => _recordings = items);
    }
  }

  Future<void> _handleSynthesize() async {
    final text = _ttsController.text.trim();
    if (text.isEmpty || _isProcessing) return;

    setState(() {
      _isProcessing = true;
      _statusMessage = null;
    });

    try {
      final res = await widget.bridgeService.synthesizeSpeech(text, voice: _selectedVoice);
      if (mounted) {
        if (res['success'] == true) {
          setState(() {
            _statusMessage = res['message']?.toString() ?? 'Speech synthesized successfully.';
          });
          _loadRecordings();
        } else {
          setState(() => _statusMessage = res['error']?.toString() ?? 'Synthesis failed.');
        }
      }
    } catch (e) {
      if (mounted) setState(() => _statusMessage = 'Synthesis error: $e');
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  Future<void> _handleTranscribe() async {
    if (_isProcessing) return;

    setState(() {
      _isProcessing = true;
      _statusMessage = 'Listening & transcribing speech stream...';
    });

    try {
      final res = await widget.bridgeService.transcribeAudio();
      if (mounted) {
        if (res['success'] == true) {
          setState(() {
            _liveTranscription = res['text']?.toString() ?? '';
            _statusMessage = 'Speech transcription complete (${res['duration']}s).';
          });
        }
      }
    } catch (e) {
      if (mounted) setState(() => _statusMessage = 'Transcription error: $e');
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppTheme.bgDark,
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [Color(0xFF06B6D4), Color(0xFF3B82F6)]),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.graphic_eq, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Echo — All-in-One Audio Core',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      'Speech-to-text audio transcription, natural text-to-speech synthesis, and voice commands.',
                      style: TextStyle(fontSize: 12, color: AppTheme.textMuted),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.refresh, size: 18, color: AppTheme.textMuted),
                tooltip: 'Refresh Recordings',
                onPressed: _loadRecordings,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Main Workspace
          Expanded(
            child: Row(
              children: [
                // Left: Voice Input & Transcription
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: AppTheme.bgSurface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppTheme.borderColor),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'VOICE RECOGNITION & TRANSCRIPTION (STT)',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 12),
                        Center(
                          child: InkWell(
                            onTap: _isProcessing ? null : _handleTranscribe,
                            borderRadius: BorderRadius.circular(50),
                            child: Container(
                              width: 80,
                              height: 80,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: const Color(0xFF06B6D4).withValues(alpha: 0.15),
                                border: Border.all(color: const Color(0xFF06B6D4), width: 2),
                              ),
                              child: Icon(
                                _isProcessing ? Icons.mic_none : Icons.mic,
                                size: 36,
                                color: const Color(0xFF06B6D4),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 10),
                        const Center(
                          child: Text(
                            'Click Microphone to Transcribe Voice Input',
                            style: TextStyle(fontSize: 11, color: AppTheme.textMuted),
                          ),
                        ),
                        const SizedBox(height: 16),
                        const Text('Live Transcription Output', style: TextStyle(fontSize: 11, color: AppTheme.textMuted)),
                        const SizedBox(height: 6),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppTheme.bgDark,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: AppTheme.borderColor),
                          ),
                          child: Text(
                            _liveTranscription.isNotEmpty ? _liveTranscription : 'Press microphone or say "Echo transcribe"...',
                            style: TextStyle(
                              fontSize: 12,
                              color: _liveTranscription.isNotEmpty ? AppTheme.textMain : AppTheme.textMuted,
                              fontStyle: _liveTranscription.isNotEmpty ? FontStyle.normal : FontStyle.italic,
                            ),
                          ),
                        ),
                        const Spacer(),
                        if (_statusMessage != null)
                          Text(_statusMessage!, style: const TextStyle(fontSize: 11, color: Color(0xFF10B981))),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 18),

                // Right: TTS Voice Synthesis & History
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: AppTheme.bgSurface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppTheme.borderColor),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'SPEECH SYNTHESIS (TTS)',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _ttsController,
                          maxLines: 3,
                          style: const TextStyle(fontSize: 13, color: AppTheme.textMain),
                          decoration: InputDecoration(
                            hintText: 'Enter text to speak aloud (e.g. "Inventory status verified, zero anomalies found")...',
                            hintStyle: const TextStyle(fontSize: 12, color: AppTheme.textMuted),
                            filled: true,
                            fillColor: AppTheme.bgDark,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                              borderSide: const BorderSide(color: AppTheme.borderColor),
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                value: _selectedVoice,
                                dropdownColor: AppTheme.bgSurface,
                                style: const TextStyle(fontSize: 12, color: AppTheme.textMain),
                                decoration: InputDecoration(
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                  filled: true,
                                  fillColor: AppTheme.bgDark,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(6),
                                    borderSide: const BorderSide(color: AppTheme.borderColor),
                                  ),
                                ),
                                items: _voices.map((v) => DropdownMenuItem(value: v, child: Text('VOICE: ${v.toUpperCase()}'))).toList(),
                                onChanged: (val) => setState(() => _selectedVoice = val ?? 'nova'),
                              ),
                            ),
                            const SizedBox(width: 10),
                            ElevatedButton.icon(
                              onPressed: _isProcessing ? null : _handleSynthesize,
                              icon: const Icon(Icons.volume_up, size: 16),
                              label: const Text('Speak', style: TextStyle(fontWeight: FontWeight.bold)),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF06B6D4),
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        const Divider(color: AppTheme.borderColor),
                        const Text(
                          'SYNTHESIS HISTORY',
                          style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.textMuted, letterSpacing: 0.5),
                        ),
                        const SizedBox(height: 8),
                        Expanded(
                          child: _recordings.isEmpty
                              ? const Center(child: Text('No synthesized audio tracks yet.', style: TextStyle(fontSize: 11, color: AppTheme.textMuted)))
                              : ListView.separated(
                                  itemCount: _recordings.length,
                                  separatorBuilder: (_, __) => const Divider(color: AppTheme.borderColor, height: 1),
                                  itemBuilder: (context, idx) {
                                    final item = _recordings[idx];
                                    return ListTile(
                                      dense: true,
                                      contentPadding: EdgeInsets.zero,
                                      leading: const Icon(Icons.audiotrack, size: 18, color: Color(0xFF06B6D4)),
                                      title: Text(item['text'] ?? '', style: const TextStyle(fontSize: 12, color: AppTheme.textMain), maxLines: 1),
                                      subtitle: Text('${item['voice']} • ${item['duration']}s • ${item['audio_format']}', style: const TextStyle(fontSize: 10, color: AppTheme.textMuted)),
                                    );
                                  },
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
