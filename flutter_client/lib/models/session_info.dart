class SessionInfo {
  final String sessionId;
  final String appName;
  final String binaryPath;
  final int pid;
  final String status;
  final String runtime;
  final String createdAt;
  final int? exitCode;
  final List<String> recentLogs;

  SessionInfo({
    required this.sessionId,
    required this.appName,
    required this.binaryPath,
    required this.pid,
    required this.status,
    this.runtime = 'local_native',
    this.createdAt = '',
    this.exitCode,
    this.recentLogs = const [],
  });

  factory SessionInfo.fromJson(Map<String, dynamic> json) {
    return SessionInfo(
      sessionId: json['session_id'] ?? '',
      appName: json['app_name'] ?? json['binary_path'] ?? 'App Process',
      binaryPath: json['binary_path'] ?? '',
      pid: json['pid'] is int ? json['pid'] : int.tryParse(json['pid']?.toString() ?? '0') ?? 0,
      status: json['status'] ?? 'unknown',
      runtime: json['runtime'] ?? 'local_native',
      createdAt: json['created_at'] ?? '',
      exitCode: json['exit_code'] as int?,
      recentLogs: (json['recent_logs'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'session_id': sessionId,
      'app_name': appName,
      'binary_path': binaryPath,
      'pid': pid,
      'status': status,
      'runtime': runtime,
      'created_at': createdAt,
      'exit_code': exitCode,
      'recent_logs': recentLogs,
    };
  }

  SessionInfo copyWith({
    String? status,
    int? exitCode,
    List<String>? recentLogs,
  }) {
    return SessionInfo(
      sessionId: sessionId,
      appName: appName,
      binaryPath: binaryPath,
      pid: pid,
      status: status ?? this.status,
      runtime: runtime,
      createdAt: createdAt,
      exitCode: exitCode ?? this.exitCode,
      recentLogs: recentLogs ?? this.recentLogs,
    );
  }
}
