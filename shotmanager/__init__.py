import logging
import os
from pathlib import Path

import bpy
from bpy.app.handlers import persistent

from bpy.props import BoolProperty, IntProperty, FloatProperty

from . import otio
from . import rendering

from .config import config

from .handlers import jump_to_shot

from .operators import takes
from .operators import shots
from .operators import shots_global_settings

from .operators import general
from .operators import playbar
from .operators import shots_toolbar

from .operators import prefs
from .operators import about

from .properties import props
from .properties import addon_prefs

from .retimer import retimer_ui
from .retimer import retimer_props

from .scripts import precut_tools

from .tools import vse_render

from .ui import sm_ui

from .utils import utils
from .utils import utils_render
from .utils import utils_handlers
from .utils import utils_operators

from . import videoshotmanager
from . import viewport_3d

from .scripts import rrs

from .data_patches.data_patch_to_v1_2_25 import data_patch_to_v1_2_25
from .data_patches.data_patch_to_v1_3_16 import data_patch_to_v1_3_16

from .debug import sm_debug

bl_info = {
    "name": "UAS Shot Manager",
    "author": "Julien Blervaque (aka Werwack), Romain Carriquiry Borchiari",
    "description": "Manage a sequence of shots and cameras in the 3D View - Ubisoft Animation Studio",
    "blender": (2, 83, 1),
    "version": (1, 3, 16),
    "location": "View3D > UAS Shot Manager",
    "wiki_url": "https://gitlab-ncsa.ubisoft.org/animation-studio/blender/shotmanager-addon/-/wikis/home",
    "warning": "",
    "category": "UAS",
}

__version__ = f"v{bl_info['version'][0]}.{bl_info['version'][1]}.{bl_info['version'][2]}"


###########
# Logging
###########

_logger = logging.getLogger(__name__)
_logger.propagate = True
MODULE_PATH = Path(__file__).parent.parent
logging.basicConfig(level=logging.DEBUG)
_logger.setLevel(logging.INFO)  # CRITICAL ERROR WARNING INFO DEBUG NOTSET

pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)

# _logger.info("Logger info")
# _logger.warning(f"logger warning")
# _logger.error("logger error")


class Formatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record: logging.LogRecord):
        """
        The role of this custom formatter is:
        - append filepath and lineno to logging format but shorten path to files, to make logs more clear
        - to append "./" at the begining to permit going to the line quickly with VS Code CTRL+click from terminal
        """
        s = super().format(record)
        pathname = Path(record.pathname).relative_to(MODULE_PATH)
        s += f" [{os.curdir}{os.sep}{pathname}:{record.lineno}]"
        return s


# def get_logs_directory():
#     def _get_logs_directory():
#         import tempfile

#         if "MIXER_USER_LOGS_DIR" in os.environ:
#             username = os.getlogin()
#             base_shared_path = Path(os.environ["MIXER_USER_LOGS_DIR"])
#             if os.path.exists(base_shared_path):
#                 return os.path.join(os.fspath(base_shared_path), username)
#             logger.error(
#                 f"MIXER_USER_LOGS_DIR env var set to {base_shared_path}, but directory does not exists. Falling back to default location."
#             )
#         return os.path.join(os.fspath(tempfile.gettempdir()), "mixer")

#     dir = _get_logs_directory()
#     if not os.path.exists(dir):
#         os.makedirs(dir)
#     return dir


# def get_log_file():
#     from mixer.share_data import share_data

#     return os.path.join(get_logs_directory(), f"mixer_logs_{share_data.run_id}.log")


###########
# Handlers
###########


def timeline_valueChanged(self, context):
    print("  timeline_valueChanged:  self.UAS_shot_manager_display_timeline: ", self.UAS_shot_manager_display_timeline)
    if self.UAS_shot_manager_display_timeline:
        bpy.ops.uas_shot_manager.draw_timeline("INVOKE_DEFAULT")
        # bpy.ops.uas_shot_manager.draw_cameras_ui("INVOKE_DEFAULT")


def install_shot_handler(self, context):
    if self.UAS_shot_manager_shots_play_mode and jump_to_shot not in bpy.app.handlers.frame_change_pre:
        scene = context.scene
        shots = scene.UAS_shot_manager_props.get_shots()
        for i, shot in enumerate(shots):
            if shot.start <= scene.frame_current <= shot.end:
                scene.UAS_shot_manager_props.current_shot_index = i
                break
        bpy.app.handlers.frame_change_pre.append(jump_to_shot)
    #     bpy.app.handlers.frame_change_post.append(jump_to_shot__frame_change_post)

    #    bpy.ops.uas_shot_manager.draw_timeline ( "INVOKE_DEFAULT" )
    elif not self.UAS_shot_manager_shots_play_mode and jump_to_shot in bpy.app.handlers.frame_change_pre:
        utils_handlers.removeAllHandlerOccurences(jump_to_shot, handlerCateg=bpy.app.handlers.frame_change_pre)
        # utils_handlers.removeAllHandlerOccurences(
        #     jump_to_shot__frame_change_post, handlerCateg=bpy.app.handlers.frame_change_post
        # )


@persistent
def checkDataVersion_post_load_handler(self, context):
    loadedFileName = bpy.path.basename(bpy.context.blend_data.filepath)
    print("\n\n-------------------------------------------------------")
    if "" == loadedFileName:
        print("\nNew file loaded")
    else:
        print("\nExisting file loaded: ", bpy.path.basename(bpy.context.blend_data.filepath))
        _logger.info("  - Shot Manager is checking the version used to create the loaded scene data...")

        numScenesToUpgrade = 0
        for scn in bpy.data.scenes:
            # if "UAS_shot_manager_props" in scn:
            if getattr(bpy.context.scene, "UAS_shot_manager_props", None) is not None:
                #   print("\n   Shot Manager instance found in scene " + scn.name)
                props = scn.UAS_shot_manager_props
                #   print("     Data version: ", props.dataVersion)
                #   print("     Shot Manager version: ", bpy.context.window_manager.UAS_shot_manager_version)
                # if props.dataVersion <= 0 or props.dataVersion < bpy.context.window_manager.UAS_shot_manager_version:
                if props.dataVersion <= 0 or props.dataVersion < 1003016:
                    _logger.info("     *** Shot Manager Data Version is lower than the current Shot Manager version")
                    numScenesToUpgrade += 1
                #    props.dataVersion = -5

        if numScenesToUpgrade:
            # apply patch and apply new data version
            # wkip patch strategy to re-think. Collect the data versions and apply the respective patches?

            if props.dataVersion < 1002026:
                print("       Applying data patch to file: upgrade to 1002025")
                data_patch_to_v1_2_25()

            if props.dataVersion < 1003016:
                print("       Applying data patch to file: upgrade to 1002025")
                data_patch_to_v1_3_16()

            # set right data version
            # props.dataVersion = bpy.context.window_manager.UAS_shot_manager_version
            # print("       Data upgraded to version V. ", props.dataVersion)

    props = bpy.context.scene.UAS_shot_manager_props
    if props is not None:
        if props.display_shotname_in_3dviewport:
            try:
                bpy.ops.uas_shot_manager.draw_cameras_ui("INVOKE_DEFAULT")
            except Exception as e:
                print("Paf in draw cameras ui  *")

        if props.display_hud_in_3dviewport:
            try:
                bpy.ops.uas_shot_manager.draw_hud("INVOKE_DEFAULT")
            except Exception as e:
                print("Paf in draw hud  *")


# wkip doesn t work!!! Property values changed right before the save are not saved in the file!
# @persistent
# def checkDataVersion_save_pre_handler(self, context):
#     print("\nFile saved - Shot Manager is writing its data version in the scene")
#     for scn in bpy.data.scenes:
#         if "UAS_shot_manager_props" in scn:
#             print("\n   Shot Manager instance found in scene, writing data version: " + scn.name)
#             props.dataVersion = bpy.context.window_manager.UAS_shot_manager_version
#             print("   props.dataVersion: ", props.dataVersion)


# classes = (
#
# )


def register():

    versionTupple = utils.display_addon_registered_version("UAS Shot Manager")

    config.initGlobalVariables()
    verbose = config.uasDebug

    ###################
    # logging
    ###################

    if len(_logger.handlers) == 0:
        _logger.setLevel(logging.WARNING)
        formatter = Formatter("{asctime} {levelname[0]} {name:<36}  - {message:<80}", style="{")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        _logger.addHandler(handler)

        # handler = logging.FileHandler(get_log_file())
        # handler.setFormatter(formatter)
        # _logger.addHandler(handler)

    ###################
    # update data
    ###################

    # bpy.context.window_manager.UAS_shot_manager_version
    bpy.types.WindowManager.UAS_shot_manager_version = IntProperty(
        name="Add-on Version Int", description="Add-on version as integer", default=versionTupple[1]
    )

    # handler to check the data version at load
    ##################
    print("       * Post Load handler added\n")

    if verbose:
        utils_handlers.displayHandlers(handlerCategName="load_post")

    utils_handlers.removeAllHandlerOccurences(
        checkDataVersion_post_load_handler, handlerCateg=bpy.app.handlers.load_post
    )
    bpy.app.handlers.load_post.append(checkDataVersion_post_load_handler)

    if verbose:
        utils_handlers.displayHandlers(handlerCategName="load_post")

    # handler to write the data version at save
    ##################
    # print("       - Pre Save handler added")
    # if verbose:
    #     utils_handlers.displayHandlers(handlerCategName="save_pre")

    # utils_handlers.removeAllHandlerOccurences(checkDataVersion_save_pre_handler, handlerCateg=bpy.app.handlers.save_pre)
    # bpy.app.handlers.save_pre.append(checkDataVersion_save_pre_handler)

    # if verbose:
    #     utils_handlers.displayHandlers(handlerCategName="save_pre")

    # initialization
    ##################

    # data version is written in the initialize function
    bpy.types.WindowManager.UAS_shot_manager_isInitialized = BoolProperty(
        name="Shot Manager is initialized", description="", default=False
    )

    # utils_handlers.displayHandlers()
    utils_handlers.removeAllHandlerOccurences(jump_to_shot, handlerCateg=bpy.app.handlers.frame_change_pre)
    # utils_handlers.removeAllHandlerOccurences(
    #     jump_to_shot__frame_change_post, handlerCateg=bpy.app.handlers.frame_change_post
    # )
    # utils_handlers.displayHandlers()

    # for cls in classes:
    #     bpy.utils.register_class(cls)

    addon_prefs.register()

    utils_operators.register()

    # operators
    takes.register()
    shots.register()
    shots_global_settings.register()
    precut_tools.register()
    playbar.register()
    retimer_props.register()
    props.register()
    shots_toolbar.register()

    # ui
    sm_ui.register()
    rrs.register()
    retimer_ui.register()

    rendering.register()
    otio.register()
    vse_render.register()
    utils_render.register()
    general.register()
    viewport_3d.register()
    videoshotmanager.register()
    prefs.register()
    about.register()

    # debug tools

    if config.uasDebug:
        sm_debug.register()

    # declaration of properties that will not be saved in the scene:
    ####################

    # call in the code by context.window_manager.UAS_shot_manager_shots_play_mode etc

    bpy.types.WindowManager.UAS_shot_manager_shots_play_mode = BoolProperty(
        name="frame_handler",
        description="Override the standard animation Play mode to play the enabled shots\nin the specified order",
        default=False,
        update=install_shot_handler,
    )

    bpy.types.WindowManager.UAS_shot_manager_display_timeline = BoolProperty(
        name="display_timeline",
        description="Display a timeline in the 3D Viewport with the shots in the specified order",
        default=False,
        update=timeline_valueChanged,
    )

    bpy.types.WindowManager.UAS_shot_manager_progressbar = FloatProperty(
        name="progressbar",
        description="Value of the progress bar",
        subtype="PERCENTAGE",
        min=0,
        max=100,
        precision=0,
        default=0,
        options=set(),
    )


def unregister():

    print("\n*** --- Unregistering UAS Shot Manager Add-on --- ***\n")

    #    bpy.context.scene.UAS_shot_manager_props.display_shotname_in_3dviewport = False

    utils_handlers.removeAllHandlerOccurences(
        checkDataVersion_post_load_handler, handlerCateg=bpy.app.handlers.load_post
    )

    # debug tools
    if config.uasDebug:
        sm_debug.unregister()

    # ui
    about.unregister()
    prefs.unregister()
    videoshotmanager.unregister()
    viewport_3d.unregister()
    general.unregister()
    utils_render.unregister()
    vse_render.unregister()
    otio.unregister()
    rendering.unregister()

    retimer_ui.unregister()
    rrs.unregister()
    sm_ui.unregister()

    # operators
    shots_toolbar.unregister()
    props.unregister()
    retimer_props.unregister()
    playbar.unregister()
    precut_tools.unregister()
    shots_global_settings.unregister()
    shots.unregister()
    takes.unregister()
    utils_operators.unregister()

    addon_prefs.unregister()

    # for cls in reversed(classes):
    #     bpy.utils.unregister_class(cls)

    if jump_to_shot in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(jump_to_shot)

    del bpy.types.WindowManager.UAS_shot_manager_shots_play_mode
    del bpy.types.WindowManager.UAS_shot_manager_display_timeline

    del bpy.types.WindowManager.UAS_shot_manager_isInitialized
    del bpy.types.WindowManager.UAS_shot_manager_version

    config.releaseGlobalVariables()
