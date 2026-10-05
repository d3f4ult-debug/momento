import 'dart:async';
import 'package:flutter/material.dart';
import '../models/app_info.dart';
import '../models/chat_message.dart';
import '../models/session_info.dart';
import '../services/bridge_service.dart';
import '../theme/app_theme.dart';
import '../widgets/chat_message_bubble.dart';
import '../widgets/onboarding_dialog.dart';
import '../widgets/settings_dialog.dart';
import '../widgets/sidebar.dart';

class DashboardScreen extends StatefulWidget {
  final BridgeService bridgeService;

  const DashboardScreen({
    super.key,
    required this.bridgeService,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  List<AppInfo> _apps = [];
  List<SessionInfo> _sessions = [];
  final List<ChatMessage> _messages = [];

  bool _isSending = false;
  Timer? _sessionPollTimer;

  @override
  void initState() {
    super.initState();
    _initDashboard();
  }

  @override
  void dispose() {
    _sessionPollTimer?.cancel();
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _initDashboard() async {
    // Add initial welcome message
    _messages.add(
      ChatMessage(
        id: 'welcome',
        sender: MessageSender.momento,
        text: 'Welcome to Momento Desktop Workspace!\n\n'
            'I can launch, monitor, and automate any application on your Windows machine or '
            'inside your Contabo VPS Wine sandbox container.\n\n'
            'Type in plain human language (e.g. "Momento, open notepad") or click any prompt below.',
        timestamp: DateTime.now(),
      ),
    );

    final state = await widget.bridgeService.fetchInitialState();
    if (mounted) {
      final rawApps = state['discovered_apps'] as List<dynamic>? ?? [];
      final rawSessions = state['active_sessions'] as List<dynamic>? ?? [];

      setState(() {
        _apps = rawApps.map((e) => AppInfo.fromJson(e as Map<String, dynamic>)).toList();
        _sessions = rawSessions.map((e) => SessionInfo.fromJson(e as Map<String, dynamic>)).toList();
      });

      // If onboarding is not completed, display setup dialog
      if (!(state['setup_completed'] ?? false)) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _showOnboardingDialog();
        });
      }
    }

    // Start background poller for active sessions
    _sessionPollTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      _pollActiveSessions();
    });
  }

  Future<void> _showOnboardingDialog() async {
    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) {
        return OnboardingDialog(
          initialBackendUrl: widget.bridgeService.backendUrl,
          onComplete: (url) async {
            final res = await widget.bridgeService.grantPermissions(newBackendUrl: url);
            final rawApps = res['apps'] as List<dynamic>? ?? [];
            setState(() {
              _apps = rawApps.map((e) => AppInfo.fromJson(e as Map<String, dynamic>)).toList();
            });
            _addMomentoMessage(
              'Setup Complete! Successfully cataloged ${_apps.length} applications from your machine. '
              'You can now open any app naturally.',
            );
          },
        );
      },
    );
  }

  Future<void> _pollActiveSessions() async {
    final state = await widget.bridgeService.fetchInitialState();
    if (!mounted) return;

    final rawSessions = state['active_sessions'] as List<dynamic>? ?? [];
    final updated = rawSessions.map((e) => SessionInfo.fromJson(e as Map<String, dynamic>)).toList();

    setState(() {
      _sessions = updated;
    });

    // Also update any execution cards in messages that are still running
    for (int i = 0; i < _messages.length; i++) {
      final msg = _messages[i];
      if (msg.executionResult != null && msg.executionResult!.status.toLowerCase() == 'running') {
        final logsRes = await widget.bridgeService.getSessionLogs(msg.executionResult!.sessionId);
        if (logsRes['success'] == true) {
          final logs = (logsRes['logs'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [];
          final status = logsRes['status']?.toString() ?? msg.executionResult!.status;
          if (mounted) {
            setState(() {
              _messages[i] = msg.copyWith(
                executionResult: msg.executionResult!.copyWith(
                  status: status,
                  logs: logs,
                ),
              );
            });
          }
        }
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _addUserMessage(String text) {
    setState(() {
      _messages.add(
        ChatMessage(
          id: DateTime.now().millisecondsSinceEpoch.toString(),
          sender: MessageSender.user,
          text: text,
          timestamp: DateTime.now(),
        ),
      );
    });
    _scrollToBottom();
  }

  void _addMomentoMessage(String text, {ExecutionResult? result}) {
    setState(() {
      _messages.add(
        ChatMessage(
          id: DateTime.now().millisecondsSinceEpoch.toString(),
          sender: MessageSender.momento,
          text: text,
          timestamp: DateTime.now(),
          executionResult: result,
        ),
      );
    });
    _scrollToBottom();
  }

  Future<void> _handleSendMessage([String? overrideText]) async {
    final text = overrideText ?? _inputController.text.trim();
    if (text.isEmpty || _isSending) return;

    _inputController.clear();
    _addUserMessage(text);

    setState(() => _isSending = true);

    try {
      final res = await widget.bridgeService.sendMessage(text);
      if (mounted) {
        final action = res['action']?.toString() ?? '';
        final isSuccess = res['success'] == true;

        if (action == 'launch' && isSuccess) {
          final execResult = ExecutionResult(
            success: true,
            sessionId: res['session_id'] ?? '',
            appName: res['app_name'] ?? 'Application',
            binaryPath: res['binary_path'] ?? '',
            pid: res['pid'] is int ? res['pid'] : int.tryParse(res['pid']?.toString() ?? '0') ?? 0,
            runtime: res['runtime'] ?? 'local_native',
            status: res['status'] ?? 'running',
            logs: [],
          );
          _addMomentoMessage('Launched ${execResult.appName} successfully.', result: execResult);
          _pollActiveSessions();
        } else {
          final replyText = res['message']?.toString() ?? 'Command processed.';
          _addMomentoMessage(replyText);
        }
      }
    } catch (e) {
      if (mounted) {
        _addMomentoMessage('Failed to execute command: $e');
      }
    } finally {
      if (mounted) {
        setState(() => _isSending = false);
      }
    }
  }

  Future<void> _handleStopSession(String sessionId) async {
    final stopped = await widget.bridgeService.stopSession(sessionId);
    if (mounted) {
      if (stopped) {
        _addMomentoMessage('Session "$sessionId" stopped.');
      } else {
        _addMomentoMessage('Could not stop session "$sessionId".');
      }
      _pollActiveSessions();
    }
  }

  Future<void> _handleRescan() async {
    _addMomentoMessage('Scanning local machine for installed software...');
    final updatedApps = await widget.bridgeService.rescanApps();
    if (mounted) {
      setState(() => _apps = updatedApps);
      _addMomentoMessage('Scan complete! Found ${_apps.length} applications.');
    }
  }

  void _showSettingsDialog() {
    showDialog(
      context: context,
      builder: (context) {
        return SettingsDialog(
          currentUrl: widget.bridgeService.backendUrl,
          currentMode: widget.bridgeService.executionMode,
          onSave: (newUrl, newMode) async {
            await widget.bridgeService.saveSettings(newUrl: newUrl, newMode: newMode);
            setState(() {});
            _addMomentoMessage('Settings updated. Backend: $newUrl | Mode: $newMode');
          },
        );
      },
    );
  }

  void _clearChat() {
    setState(() {
      _messages.clear();
      _messages.add(
        ChatMessage(
          id: 'cleared',
          sender: MessageSender.momento,
          text: 'Chat history cleared. Ready for your next command.',
          timestamp: DateTime.now(),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          // Left Sidebar
          Sidebar(
            apps: _apps,
            sessions: _sessions,
            executionMode: widget.bridgeService.executionMode,
            backendUrl: widget.bridgeService.backendUrl,
            onModeChanged: (mode) {
              setState(() => widget.bridgeService.executionMode = mode);
              widget.bridgeService.saveSettings(
                newUrl: widget.bridgeService.backendUrl,
                newMode: mode,
              );
            },
            onLaunchApp: (app) => _handleSendMessage('Momento, open ${app.id}'),
            onStopSession: _handleStopSession,
            onRescan: _handleRescan,
            onOpenSettings: _showSettingsDialog,
          ),

          // Right Main Area
          Expanded(
            child: Column(
              children: [
                // Chat Header
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                  decoration: const BoxDecoration(
                    color: AppTheme.bgSurface,
                    border: Border(bottom: BorderSide(color: AppTheme.borderColor)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Natural Language Execution Workspace',
                              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.textMain),
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Target: ${widget.bridgeService.backendUrl} • Mode: ${widget.bridgeService.executionMode.toUpperCase()}',
                              style: const TextStyle(fontSize: 11, color: AppTheme.textMuted),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton.icon(
                        onPressed: _clearChat,
                        icon: const Icon(Icons.delete_outline, size: 14),
                        label: const Text('Clear Chat', style: TextStyle(fontSize: 11)),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppTheme.textMuted,
                          side: const BorderSide(color: AppTheme.borderColor),
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                        ),
                      ),
                    ],
                  ),
                ),

                // Chat Messages Stream
                Expanded(
                  child: ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.all(24),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final msg = _messages[index];
                      return ChatMessageBubble(
                        message: msg,
                        onStopExecution: msg.executionResult != null
                            ? () => _handleStopSession(msg.executionResult!.sessionId)
                            : null,
                      );
                    },
                  ),
                ),

                // Quick Suggestions Chips & Input Bar
                Container(
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 16),
                  decoration: const BoxDecoration(
                    color: AppTheme.bgSurface,
                    border: Border(top: BorderSide(color: AppTheme.borderColor)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Suggestions
                      SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            _buildSuggestionChip('Open Notepad'),
                            _buildSuggestionChip('Run Calculator'),
                            _buildSuggestionChip('Open Chrome'),
                            _buildSuggestionChip('List active sessions'),
                            _buildSuggestionChip('Rescan installed apps'),
                          ],
                        ),
                      ),
                      const SizedBox(height: 10),

                      // Input Bar
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _inputController,
                              style: const TextStyle(fontSize: 13),
                              decoration: const InputDecoration(
                                hintText: 'Momento, can you open Notepad for me?',
                              ),
                              onSubmitted: (val) => _handleSendMessage(),
                            ),
                          ),
                          const SizedBox(width: 10),
                          ElevatedButton.icon(
                            onPressed: _isSending ? null : () => _handleSendMessage(),
                            icon: _isSending
                                ? const SizedBox(
                                    width: 14,
                                    height: 14,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : const Icon(Icons.send_rounded, size: 16),
                            label: const Text('Send', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.accent,
                              foregroundColor: Colors.white,
                              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSuggestionChip(String label) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: ActionChip(
        label: Text(label, style: const TextStyle(fontSize: 11, color: AppTheme.textMuted)),
        backgroundColor: AppTheme.bgCard,
        side: const BorderSide(color: AppTheme.borderColor),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        onPressed: () => _handleSendMessage(label),
      ),
    );
  }
}
