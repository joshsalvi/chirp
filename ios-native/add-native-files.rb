#!/usr/bin/env ruby
# Adds Chirp's own iPhone/iPad files (ios-native/*.swift, copied into
# ios/App/App/ by build-ios.sh) to the App target, and bundles every
# AppIcon-<theme> set as an alternate icon. Safe to run again.
#
#   ruby add-native-files.rb ios/App/App.xcodeproj
require 'xcodeproj'

proj_path = ARGV[0] or abort 'usage: add-native-files.rb <project>'
project = Xcodeproj::Project.open(proj_path)
app = project.targets.find { |t| t.name == 'App' } or abort 'No App target'
group = project.main_group.find_subpath('App', false) or abort 'No App group'
root = File.dirname(proj_path)
%w[ChirpBridgeViewController.swift ChirpAppIconPlugin.swift].each do |name|
  abort "Missing #{root}/App/#{name}" unless File.exist?(File.join(root, 'App', name))
  next if group.files.any? { |f| f.path == name }
  app.add_file_references([group.new_reference(name)])
end
app.build_configurations.each do |c|
  c.build_settings['ASSETCATALOG_COMPILER_INCLUDE_ALL_APPICON_ASSETS'] = 'YES'
end
project.save
puts 'Chirp native files and theme icons added'
