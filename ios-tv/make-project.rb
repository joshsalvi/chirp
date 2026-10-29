#!/usr/bin/env ruby
# Creates ios-tv/build/ChirpTV.xcodeproj for the Apple TV app (build-tvos.sh
# runs it; safe to run again, it starts fresh each time).
#   ruby make-project.rb <bundle id> [team id]
require 'xcodeproj'
require 'fileutils'

bundle_id, team = ARGV
abort 'usage: make-project.rb <bundle id> [team id]' unless bundle_id
root = File.expand_path(__dir__)
build = File.join(root, 'build')
FileUtils.rm_rf(File.join(build, 'ChirpTV.xcodeproj'))
FileUtils.mkdir_p(build)
project = Xcodeproj::Project.new(File.join(build, 'ChirpTV.xcodeproj'))
target = project.new_target(:application, 'ChirpTV', :tvos, '17.0')
group = project.main_group.new_group('ChirpTV', File.join(root, 'ChirpTV'))
Dir.glob(File.join(root, 'ChirpTV', '*.swift')).sort.each do |path|
  target.add_file_references([group.new_reference(path)])
end
target.add_resources([group.new_reference(File.join(root, 'ChirpTV', 'Assets.xcassets'))])

target.build_configurations.each do |c|
  s = c.build_settings
  s['PRODUCT_NAME'] = 'Chirp'
  s['PRODUCT_BUNDLE_IDENTIFIER'] = bundle_id
  s['SDKROOT'] = 'appletvos'
  s['SUPPORTED_PLATFORMS'] = 'appletvos appletvsimulator'
  s['TARGETED_DEVICE_FAMILY'] = '3'
  s['TVOS_DEPLOYMENT_TARGET'] = '17.0'
  s['SWIFT_VERSION'] = '5.0'
  s['GENERATE_INFOPLIST_FILE'] = 'YES'
  s['INFOPLIST_KEY_CFBundleDisplayName'] = 'Chirp'
  s['INFOPLIST_KEY_UILaunchScreen_Generation'] = 'YES'
  s['INFOPLIST_KEY_UIUserInterfaceStyle'] = 'Dark'
  s['INFOPLIST_KEY_ITSAppUsesNonExemptEncryption'] = 'NO'
  s['INFOPLIST_KEY_LSApplicationCategoryType'] = 'public.app-category.reference'
  # Home-network Chirp servers are often plain http://
  s['INFOPLIST_KEY_NSLocalNetworkUsageDescription'] = 'Chirp connects to a Chirp server on your home network when you choose one.'
  s['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'App Icon & Top Shelf Image'
  s['ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME'] = 'AccentColor'
  s['MARKETING_VERSION'] ||= '1.0'
  s['CURRENT_PROJECT_VERSION'] ||= '1'
  s['CODE_SIGN_STYLE'] = 'Automatic'
  s['DEVELOPMENT_TEAM'] = team if team && !team.empty?
  s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = c.name == 'Debug' ? 'DEBUG' : ''
end
project.save

# Info.plist additions GENERATE_INFOPLIST_FILE has no key for: plain http to
# any server the person types (local networks) without disabling ATS for the web.
plist = File.join(build, 'ChirpTV-Info.plist')
File.write(plist, <<~XML)
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0"><dict>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
  </dict></plist>
XML
target.build_configurations.each { |c| c.build_settings['INFOPLIST_FILE'] = plist }
project.save

# UI tests (remote focus), only when asked: UITESTS=1 ./build-tvos.sh --uitest
tests = nil
if ENV['UITESTS'] == '1'
  tests = project.new_target(:ui_test_bundle, 'ChirpTVUITests', :tvos, '17.0')
  tgroup = project.main_group.new_group('UITests', File.join(root, 'UITests'))
  Dir.glob(File.join(root, 'UITests', '*.swift')).sort.each do |path|
    tests.add_file_references([tgroup.new_reference(path)])
  end
  tests.add_dependency(target)
  tests.build_configurations.each do |c|
    s = c.build_settings
    s['PRODUCT_BUNDLE_IDENTIFIER'] = "#{bundle_id}.uitests"
    s['SDKROOT'] = 'appletvos'
    s['SUPPORTED_PLATFORMS'] = 'appletvos appletvsimulator'
    s['TARGETED_DEVICE_FAMILY'] = '3'
    s['TVOS_DEPLOYMENT_TARGET'] = '17.0'
    s['SWIFT_VERSION'] = '5.0'
    s['GENERATE_INFOPLIST_FILE'] = 'YES'
    s['TEST_TARGET_NAME'] = 'ChirpTV'
    s['CODE_SIGNING_ALLOWED'] = 'NO'
  end
  project.save
end

scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(target)
scheme.set_launch_target(target)
scheme.add_test_target(tests) if tests
scheme.save_as(project.path, 'ChirpTV', true)
puts "ChirpTV.xcodeproj ready (#{bundle_id})"
