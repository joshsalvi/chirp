#!/usr/bin/env ruby
# Creates ios-lite/build/ChirpLite.xcodeproj for the Chirp Lite app
# (build-lite.sh runs it; safe to run again).
#   ruby make-project.rb <bundle id> [team id] [marketing version] [build number]
require 'xcodeproj'
require 'fileutils'

bundle_id, team, version, build_number = ARGV
abort 'usage: make-project.rb <bundle id> [team id] [version] [build]' unless bundle_id
root = File.expand_path(__dir__)
build = File.join(root, 'build')
FileUtils.rm_rf(File.join(build, 'ChirpLite.xcodeproj'))
FileUtils.mkdir_p(build)

project = Xcodeproj::Project.new(File.join(build, 'ChirpLite.xcodeproj'))
app = project.new_target(:application, 'ChirpLite', :ios, '17.0')
group = project.main_group.new_group('ChirpLite', File.join(root, 'ChirpLite'))
Dir.glob(File.join(root, 'ChirpLite', '*.swift')).sort.each { |p| app.add_file_references([group.new_reference(p)]) }
app.add_resources([group.new_reference(File.join(root, 'ChirpLite', 'Assets.xcassets'))])

app.build_configurations.each do |c|
  s = c.build_settings
  s['PRODUCT_NAME'] = 'ChirpLite'
  s['PRODUCT_BUNDLE_IDENTIFIER'] = bundle_id
  s['TARGETED_DEVICE_FAMILY'] = '1'
  s['IPHONEOS_DEPLOYMENT_TARGET'] = '17.0'
  s['SWIFT_VERSION'] = '5.0'
  s['GENERATE_INFOPLIST_FILE'] = 'YES'
  s['INFOPLIST_KEY_CFBundleDisplayName'] = 'Chirp Lite'
  s['INFOPLIST_KEY_UILaunchScreen_Generation'] = 'YES'
  s['INFOPLIST_KEY_UISupportedInterfaceOrientations'] = 'UIInterfaceOrientationPortrait'
  s['INFOPLIST_KEY_ITSAppUsesNonExemptEncryption'] = 'NO'
  s['INFOPLIST_KEY_LSApplicationCategoryType'] = 'public.app-category.lifestyle'
  # Home-network Chirp servers are plain http.
  s['INFOPLIST_KEY_NSLocalNetworkUsageDescription'] = 'Chirp Lite connects to a Chirp server on your home network when you enter its address.'
  s['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
  s['ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME'] = 'AccentColor'
  s['MARKETING_VERSION'] = version || '1.0'
  s['CURRENT_PROJECT_VERSION'] = build_number || '1'
  s['CODE_SIGN_STYLE'] = 'Automatic'
  s['DEVELOPMENT_TEAM'] = team if team && !team.empty?
  s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = c.name == 'Debug' ? 'DEBUG' : ''
  s['INFOPLIST_FILE'] = File.join(root, 'Info.plist')
end

tests = project.new_target(:unit_test_bundle, 'ChirpLiteTests', :ios, '17.0')
tgroup = project.main_group.new_group('Tests', File.join(root, 'Tests'))
Dir.glob(File.join(root, 'Tests', '*.swift')).sort.each { |p| tests.add_file_references([tgroup.new_reference(p)]) }
tests.add_dependency(app)
tests.build_configurations.each do |c|
  s = c.build_settings
  s['PRODUCT_BUNDLE_IDENTIFIER'] = "#{bundle_id}.tests"
  s['IPHONEOS_DEPLOYMENT_TARGET'] = '17.0'
  s['SWIFT_VERSION'] = '5.0'
  s['GENERATE_INFOPLIST_FILE'] = 'YES'
  s['TEST_HOST'] = '$(BUILT_PRODUCTS_DIR)/ChirpLite.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/ChirpLite'
  s['BUNDLE_LOADER'] = '$(TEST_HOST)'
  s['CODE_SIGNING_ALLOWED'] = 'NO'
end
project.save

scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(app)
scheme.set_launch_target(app)
scheme.add_test_target(tests)
scheme.save_as(project.path, 'ChirpLite', true)
puts "ChirpLite.xcodeproj ready (#{bundle_id})"
