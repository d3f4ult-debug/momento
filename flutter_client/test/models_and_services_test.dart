import 'package:flutter_test/flutter_test.dart';
import 'package:momento_desktop/models/app_info.dart';
import 'package:momento_desktop/models/chat_message.dart';
import 'package:momento_desktop/models/session_info.dart';
import 'package:momento_desktop/services/bridge_service.dart';

void main() {
  group('Models Serialization', () {
    test('AppInfo fromJson and toJson', () {
      final json = {
        'id': 'notepad',
        'name': 'Notepad',
        'binary_path': r'C:\Windows\System32\notepad.exe',
        'category': 'utility',
        'aliases': ['notepad', 'notes'],
        'source': 'system_catalog',
      };

      final app = AppInfo.fromJson(json);
      expect(app.id, 'notepad');
      expect(app.name, 'Notepad');
      expect(app.binaryPath, r'C:\Windows\System32\notepad.exe');
      expect(app.aliases, contains('notes'));

      final back = app.toJson();
      expect(back['id'], 'notepad');
    });

    test('SessionInfo fromJson and copyWith', () {
      final json = {
        'session_id': 'sbx_test_123',
        'app_name': 'Calculator',
        'binary_path': 'calc.exe',
        'pid': 4096,
        'status': 'running',
        'runtime': 'local_native',
        'recent_logs': ['Started', 'Ready'],
      };

      final session = SessionInfo.fromJson(json);
      expect(session.sessionId, 'sbx_test_123');
      expect(session.pid, 4096);
      expect(session.status, 'running');

      final updated = session.copyWith(status: 'terminated', exitCode: 0);
      expect(updated.status, 'terminated');
      expect(updated.exitCode, 0);
    });

    test('ChatMessage and ExecutionResult', () {
      final exec = ExecutionResult(
        success: true,
        sessionId: 'sbx_abc',
        appName: 'Chrome',
        binaryPath: 'chrome.exe',
        pid: 1234,
        logs: ['Log 1', 'Log 2'],
      );

      final msg = ChatMessage(
        id: 'msg_1',
        sender: MessageSender.momento,
        text: 'Launched Chrome successfully.',
        timestamp: DateTime.now(),
        executionResult: exec,
      );

      expect(msg.sender, MessageSender.momento);
      expect(msg.executionResult?.pid, 1234);
      expect(msg.executionResult?.logs.length, 2);
    });
  });

  group('BridgeService Configuration', () {
    test('Initialization with default and custom URLs', () {
      final defaultBridge = BridgeService();
      expect(defaultBridge.backendUrl, 'http://161.97.64.38:8000');
      expect(defaultBridge.executionMode, 'hybrid');

      final customBridge = BridgeService(
        initialUrl: 'http://127.0.0.1:8000/',
        initialMode: 'local',
      );
      expect(customBridge.backendUrl, 'http://127.0.0.1:8000');
      expect(customBridge.executionMode, 'local');
    });
  });
}
