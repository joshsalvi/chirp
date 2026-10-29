#!/usr/bin/env ruby
# Adds the Apple Watch app to Capacitor's generated Xcode project. Run by
# build-ios.sh (WATCH=1) after `npx cap sync ios`; safe to run again.
#
#   ruby add-watch-target.rb ios/App/App.xcodeproj <iPhone bundle ID> <team ID> [KEY=VALUE ...]
#
# KEY=VALUE pairs are set on the iPhone (App) target only. build-ios.sh
# passes PRODUCT_BUNDLE_IDENTIFIER, TARGETED_DEVICE_FAMILY and
# CODE_SIGN_ENTITLEMENTS here instead of on the xcodebuild command line,
# where they would apply to the watch app too.
#
#   ruby add-watch-target.rb ios/App/App.xcodeproj --remove
#
# --remove takes the watch app and the iPhone-side files back out, for a
# build without WATCH=1 (the ios/ folder is kept between builds).
#
# Expects build-ios.sh to have copied ios-watch/phone/*.swift into
# ios/App/App/ and ios-watch/ChirpWatch into ios/App/ChirpWatch.
require 'xcodeproj'

proj_path, bundle_id, team, *app_settings = ARGV
abort 'usage: add-watch-target.rb <project> <bundle id> [team] [KEY=VALUE ...] | --remove' unless proj_path && bundle_id

project = Xcodeproj::Project.open(proj_path)
app = project.targets.find { |t| t.name == 'App' } or abort 'No App target'
root = File.dirname(proj_path) # ios/App
# ChirpBridgeViewController.swift is added for every build by ios-native/add-native-files.rb.
PHONE_FILES = %w[ChirpWatchPlugin.swift WatchLink.swift ChirpKeychain.swift].freeze

if bundle_id == '--remove'
  watch = project.targets.find { |t| t.name == 'ChirpWatch' }
  app.copy_files_build_phases.select { |p| p.name == 'Embed Watch Content' }.each(&:remove_from_project)
  if watch
    app.dependencies.select { |d| d.target == watch }.each(&:remove_from_project)
    watch.build_phases.each { |ph| ph.files.to_a.each(&:remove_from_project) }
    watch.product_reference&.remove_from_project
    configs = watch.build_configuration_list
    watch.remove_from_project
    configs.build_configurations.to_a.each(&:remove_from_project)
    configs.remove_from_project
  end
  if (group = project.main_group.find_subpath('ChirpWatch', false))
    group.recursive_children.each do |f|
      f.build_files.each(&:remove_from_project) if f.respond_to?(:build_files)
    end
    group.remove_from_project
  end
  app_group = project.main_group.find_subpath('App', false)
  app_group&.files&.select { |f| PHONE_FILES.include?(f.path) }&.each do |f|
    f.build_files.each(&:remove_from_project)
    f.remove_from_project
  end
  # Settings WATCH=1 wrote onto the App target; the command line sets them again.
  app.build_configurations.each do |c|
    %w[PRODUCT_BUNDLE_IDENTIFIER TARGETED_DEVICE_FAMILY CODE_SIGN_ENTITLEMENTS].each { |k| c.build_settings.delete(k) }
  end
  project.save
  puts 'Watch app removed from the Xcode project'
  exit 0
end

# ── iPhone side: the ChirpWatch plugin and the bridge view controller ──────
app_group = project.main_group.find_subpath('App', false) or abort 'No App group'
PHONE_FILES.each do |name|
  next if app_group.files.any? { |f| f.path == name }
  abort "Missing #{root}/App/#{name}" unless File.exist?(File.join(root, 'App', name))
  app.add_file_references([app_group.new_reference(name)])
end

app.build_configurations.each do |c|
  app_settings.each do |kv|
    k, v = kv.split('=', 2)
    c.build_settings[k] = v
  end
end

# ── Watch app target ───────────────────────────────────────────────────────
watch = project.targets.find { |t| t.name == 'ChirpWatch' }
unless watch
  watch = project.new_target(:application, 'ChirpWatch', :watchos, '10.0')
end

group = project.main_group.find_subpath('ChirpWatch', false) || project.main_group.new_group('ChirpWatch', 'ChirpWatch')
Dir.glob(File.join(root, 'ChirpWatch', '*.swift')).sort.each do |path|
  name = File.basename(path)
  next if group.files.any? { |f| f.path == name }
  watch.add_file_references([group.new_reference(name)])
end
unless group.files.any? { |f| f.path == 'Assets.xcassets' }
  watch.add_resources([group.new_reference('Assets.xcassets')])
end
group.new_reference('Info.plist') unless group.files.any? { |f| f.path == 'Info.plist' }

watch.build_configurations.each do |c|
  s = c.build_settings
  s['PRODUCT_NAME'] = 'ChirpWatch'
  s['PRODUCT_BUNDLE_IDENTIFIER'] = "#{bundle_id}.watchkitapp"
  s['SDKROOT'] = 'watchos'
  s['SUPPORTED_PLATFORMS'] = 'watchos watchsimulator'
  s['TARGETED_DEVICE_FAMILY'] = '4'
  s['WATCHOS_DEPLOYMENT_TARGET'] = '10.0'
  s['SWIFT_VERSION'] = '5.0'
  s['SKIP_INSTALL'] = 'YES'
  s['ENABLE_PREVIEWS'] = 'NO'
  s['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
  s['INFOPLIST_FILE'] = 'ChirpWatch/Info.plist'
  s['GENERATE_INFOPLIST_FILE'] = 'YES'
  s['INFOPLIST_KEY_CFBundleDisplayName'] = 'Chirp'
  s['INFOPLIST_KEY_WKCompanionAppBundleIdentifier'] = bundle_id
  s['INFOPLIST_KEY_WKRunsIndependentlyOfCompanionApp'] = 'NO'
  s['INFOPLIST_KEY_NSMicrophoneUsageDescription'] =
    'Chirp listens through the watch microphone to identify birds singing nearby.'
  s['INFOPLIST_KEY_NSLocationWhenInUseUsageDescription'] =
    "Chirp saves where a bird was heard with the recording and uses it to tell which birds are likely here."
  s['MARKETING_VERSION'] ||= '1.0'
  s['CURRENT_PROJECT_VERSION'] ||= '1'
  s.delete('ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME')
  s['CODE_SIGN_STYLE'] = 'Automatic'
  s['DEVELOPMENT_TEAM'] = team if team && !team.empty?
end

# ── Embed the watch app in the iPhone app ──────────────────────────────────
phase = app.copy_files_build_phases.find { |p| p.name == 'Embed Watch Content' } ||
        app.new_copy_files_build_phase('Embed Watch Content')
phase.dst_subfolder_spec = Xcodeproj::Constants::COPY_FILES_BUILD_PHASE_DESTINATIONS[:products_directory]
phase.dst_path = '$(CONTENTS_FOLDER_PATH)/Watch'
unless phase.files_references.include?(watch.product_reference)
  bf = phase.add_file_reference(watch.product_reference, true)
  bf.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }
end
app.add_dependency(watch) unless app.dependencies.any? { |d| d.target == watch }

project.save
puts "Watch app target ready (#{bundle_id}.watchkitapp)"
