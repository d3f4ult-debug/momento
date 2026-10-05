class AppInfo {
  final String id;
  final String name;
  final String binaryPath;
  final String category;
  final List<String> aliases;
  final String source;

  AppInfo({
    required this.id,
    required this.name,
    required this.binaryPath,
    this.category = 'utility',
    this.aliases = const [],
    this.source = 'system',
  });

  factory AppInfo.fromJson(Map<String, dynamic> json) {
    return AppInfo(
      id: json['id'] ?? '',
      name: json['name'] ?? json['id'] ?? 'Unknown',
      binaryPath: json['binary_path'] ?? '',
      category: json['category'] ?? 'utility',
      aliases: (json['aliases'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
      source: json['source'] ?? 'system',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'binary_path': binaryPath,
      'category': category,
      'aliases': aliases,
      'source': source,
    };
  }
}
