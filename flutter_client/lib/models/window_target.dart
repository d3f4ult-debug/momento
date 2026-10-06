class WindowTarget {
  final String title;
  final int pid;
  final String processName;
  final String processPath;
  final String workingDir;
  final int handle;
  final String className;
  final Map<String, dynamic> rect;

  WindowTarget({
    required this.title,
    required this.pid,
    required this.processName,
    required this.processPath,
    this.workingDir = '',
    this.handle = 0,
    this.className = '',
    this.rect = const {},
  });

  factory WindowTarget.fromJson(Map<String, dynamic> json) {
    return WindowTarget(
      title: json['title']?.toString() ?? '',
      pid: json['pid'] is int ? json['pid'] : int.tryParse(json['pid']?.toString() ?? '0') ?? 0,
      processName: json['process_name']?.toString() ?? '',
      processPath: json['process_path']?.toString() ?? '',
      workingDir: json['working_dir']?.toString() ?? '',
      handle: json['handle'] is int ? json['handle'] : int.tryParse(json['handle']?.toString() ?? '0') ?? 0,
      className: json['class_name']?.toString() ?? '',
      rect: json['rect'] is Map ? Map<String, dynamic>.from(json['rect'] as Map) : const {},
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'title': title,
      'pid': pid,
      'process_name': processName,
      'process_path': processPath,
      'working_dir': workingDir,
      'handle': handle,
      'class_name': className,
      'rect': rect,
    };
  }
}
