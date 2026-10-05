enum MessageSender { user, momento }

class ExecutionResult {
  final bool success;
  final String sessionId;
  final String appName;
  final String binaryPath;
  final int pid;
  final String runtime;
  final String status;
  final List<String> logs;

  ExecutionResult({
    required this.success,
    required this.sessionId,
    required this.appName,
    required this.binaryPath,
    required this.pid,
    this.runtime = 'local_native',
    this.status = 'running',
    this.logs = const [],
  });

  factory ExecutionResult.fromJson(Map<String, dynamic> json) {
    return ExecutionResult(
      success: json['success'] ?? false,
      sessionId: json['session_id'] ?? '',
      appName: json['app_name'] ?? json['binary_path'] ?? 'Application',
      binaryPath: json['binary_path'] ?? '',
      pid: json['pid'] is int ? json['pid'] : int.tryParse(json['pid']?.toString() ?? '0') ?? 0,
      runtime: json['runtime'] ?? 'local_native',
      status: json['status'] ?? 'running',
      logs: (json['logs'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
    );
  }

  ExecutionResult copyWith({
    String? status,
    List<String>? logs,
  }) {
    return ExecutionResult(
      success: success,
      sessionId: sessionId,
      appName: appName,
      binaryPath: binaryPath,
      pid: pid,
      runtime: runtime,
      status: status ?? this.status,
      logs: logs ?? this.logs,
    );
  }
}

class ChatMessage {
  final String id;
  final MessageSender sender;
  final String text;
  final DateTime timestamp;
  final ExecutionResult? executionResult;

  ChatMessage({
    required this.id,
    required this.sender,
    required this.text,
    required this.timestamp,
    this.executionResult,
  });

  ChatMessage copyWith({
    ExecutionResult? executionResult,
  }) {
    return ChatMessage(
      id: id,
      sender: sender,
      text: text,
      timestamp: timestamp,
      executionResult: executionResult ?? this.executionResult,
    );
  }
}
