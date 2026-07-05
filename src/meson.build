# -- gRPC stubs ----------------------------------------------------------
# Either regenerate from the vendored proto (needs grpcio-tools) or install
# the committed stubs as-is (Flatpak path — see meson_options.txt).
if get_option('generate_proto')
  proto_file = meson.project_source_root() / 'proto' / 'daemon.proto'
  proto_dir = meson.project_source_root() / 'proto'

  custom_target('daemon-proto',
    output: ['daemon_pb2.py', 'daemon_pb2_grpc.py'],
    command: [
      py, files('..' / 'build-aux' / 'gen-proto.py'),
      proto_dir, proto_file, '@OUTDIR@',
    ],
    install: true,
    install_dir: moduledir / 'daemon',
  )
else
  py.install_sources(
    [
      'birdie/daemon/daemon_pb2.py',
      'birdie/daemon/daemon_pb2_grpc.py',
    ],
    subdir: 'birdie/daemon',
  )
endif

# -- python sources ------------------------------------------------------
py.install_sources(
  [
    'birdie/__init__.py',
    'birdie/main.py',
    'birdie/application.py',
    'birdie/window.py',
    'birdie/async_utils.py',
    'birdie/preferences.py',
  ],
  subdir: 'birdie',
)

py.install_sources(
  [
    'birdie/daemon/__init__.py',
    'birdie/daemon/client.py',
  ],
  subdir: 'birdie/daemon',
)

py.install_sources(
  [
    'birdie/views/__init__.py',
    'birdie/views/status_view.py',
    'birdie/views/login_dialog.py',
    'birdie/views/networks_view.py',
    'birdie/views/profiles_view.py',
    'birdie/views/events_view.py',
  ],
  subdir: 'birdie/views',
)

# -- launcher ------------------------------------------------------------
launcher_conf = configuration_data()
launcher_conf.set('PYTHON', py.full_path())
launcher_conf.set('MODULE_PARENT', py.get_install_dir())

configure_file(
  input: 'birdie.in',
  output: 'birdie',
  configuration: launcher_conf,
  install: true,
  install_dir: bindir,
  install_mode: 'rwxr-xr-x',
)
