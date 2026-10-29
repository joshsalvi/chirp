#!/usr/bin/env ruby
# Creates ios-live/build/ChirpLive.xcodeproj for the Chirp Live app
# (build-live.sh runs it; safe to run again).
#   ruby make-project.rb <bundle id> [team id] [marketing version] [build number]
require 'xcodeproj'
require 'fileutils'

bundle_id, team, version, build_number = ARGV
abort 'usage: make-project.rb <bundle id> [team id] [version] [build]' unless bundle_id
root = File.expand_path(__dir__)
build = File.join(root, 'build')
FileUtils.rm_rf(File.join(build, 'ChirpLive.xcodeproj'))
FileUtils.mkdir_p(build)

project = Xcodeproj::Project.new(File.join(build, 'ChirpLive.xcodeproj'))
app = project.new_target(:application, 'ChirpLive', :ios, '17.0')
group = project.main_group.new_group('ChirpLive', File.join(root, 'ChirpLive'))
Dir.glob(File.join(root, 'ChirpLive', '*.swift')).sort.each { |p| app.add_file_references([group.new_reference(p)]) }
app.add_resources([group.new_reference(File.join(root, 'ChirpLive', 'Assets.xcassets'))])
models = project.main_group.new_group('Models', File.join(root, 'Models'))
Dir.glob(File.join(root, 'Models', '*.{tflite,txt}')).sort.each { |p| app.add_resources([models.new_reference(p)]) }

# TensorFlow Lite (build-live.sh fetches it): the Swift wrapper compiles into
# the app; the C library is a static xcframework.
vendor = project.main_group.new_group('Vendor', File.join(root, 'Vendor'))
Dir.glob(File.join(root, 'Vendor', 'TensorFlowLiteSwift', '*.swift')).sort.each { |p| app.add_file_references([vendor.new_reference(p)]) }
tflc = vendor.new_reference(File.join(root, 'Vendor', 'TensorFlowLiteC.xcframework'))
app.frameworks_build_phase.add_file_reference(tflc)

app.build_configurations.each do |c|
  s = c.build_settings
  s['PRODUCT_NAME'] = 'ChirpLive'
  s['PRODUCT_BUNDLE_IDENTIFIER'] = bundle_id
  s['TARGETED_DEVICE_FAMILY'] = '1'
  s['IPHONEOS_DEPLOYMENT_TARGET'] = '17.0'
  s['SWIFT_VERSION'] = '5.0'
  s['GENERATE_INFOPLIST_FILE'] = 'YES'
  s['INFOPLIST_KEY_CFBundleDisplayName'] = 'Chirp Live'
  s['INFOPLIST_KEY_UILaunchScreen_Generation'] = 'YES'
  s['INFOPLIST_KEY_UIUserInterfaceStyle'] = 'Dark'
  s['INFOPLIST_KEY_UISupportedInterfaceOrientations'] = 'UIInterfaceOrientationPortrait'
  s['INFOPLIST_KEY_ITSAppUsesNonExemptEncryption'] = 'NO'
  s['INFOPLIST_KEY_LSApplicationCategoryType'] = 'public.app-category.reference'
  s['INFOPLIST_KEY_NSMicrophoneUsageDescription'] = 'Chirp Live listens through the microphone to name the birds singing nearby. Sound is analyzed on your iPhone.'
  s['INFOPLIST_KEY_NSLocationWhenInUseUsageDescription'] = 'Your location narrows the list to birds found where you are at this time of year.'
  s['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
  s['ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME'] = 'AccentColor'
  s['MARKETING_VERSION'] = version || '1.0'
  s['CURRENT_PROJECT_VERSION'] = build_number || '1'
  s['CODE_SIGN_STYLE'] = 'Automatic'
  s['DEVELOPMENT_TEAM'] = team if team && !team.empty?
  s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = c.name == 'Debug' ? 'DEBUG' : ''
  s['OTHER_LDFLAGS'] = ['$(inherited)', '-lc++']
end

tests = project.new_target(:unit_test_bundle, 'ChirpLiveTests', :ios, '17.0')
tgroup = project.main_group.new_group('Tests', File.join(root, 'Tests'))
Dir.glob(File.join(root, 'Tests', '*.swift')).sort.each { |p| tests.add_file_references([tgroup.new_reference(p)]) }
Dir.glob(File.join(root, 'Tests', '*.wav')).sort.each { |p| tests.add_resources([tgroup.new_reference(p)]) }
tests.add_dependency(app)
tests.build_configurations.each do |c|
  s = c.build_settings
  s['PRODUCT_BUNDLE_IDENTIFIER'] = "#{bundle_id}.tests"
  s['IPHONEOS_DEPLOYMENT_TARGET'] = '17.0'
  s['SWIFT_VERSION'] = '5.0'
  s['GENERATE_INFOPLIST_FILE'] = 'YES'
  s['TEST_HOST'] = '$(BUILT_PRODUCTS_DIR)/ChirpLive.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/ChirpLive'
  s['BUNDLE_LOADER'] = '$(TEST_HOST)'
  s['CODE_SIGNING_ALLOWED'] = 'NO'
end
project.save

scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(app)
scheme.set_launch_target(app)
scheme.add_test_target(tests)
scheme.save_as(project.path, 'ChirpLive', true)
puts "ChirpLive.xcodeproj ready (#{bundle_id})"
