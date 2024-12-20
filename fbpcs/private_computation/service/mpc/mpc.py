#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict

import logging
from typing import Any, Dict, List, Optional, Tuple

# pyre-fixme[21]: Could not find module `fbpcp.service.container`.
from fbpcp.service.container import ContainerService

# pyre-fixme[21]: Could not find module `fbpcp.service.onedocker`.
from fbpcp.service.onedocker import OneDockerService

# pyre-fixme[21]: Could not find module
#  `fbpcs.private_computation.entity.private_computation_instance`.
from fbpcs.private_computation.entity.private_computation_instance import (
    PrivateComputationRole,
)
from fbpcs.private_computation.service.mpc.entity.mpc_instance import MPCParty
from fbpcs.private_computation.service.mpc.mpc_game import MPCGameService

# pyre-fixme[21]: Could not find module
#  `fbpcs.private_computation.service.run_binary_base_service`.
from fbpcs.private_computation.service.run_binary_base_service import (
    RunBinaryBaseService,
)

DEFAULT_BINARY_VERSION = "latest"


# pyre-fixme[11]: Annotation `RunBinaryBaseService` is not defined as a type.
class MPCService(RunBinaryBaseService):
    """MPCService is responsible for distributing a larger MPC game to multiple
    MPC workers
    """

    def __init__(
        self,
        # pyre-fixme[11]: Annotation `ContainerService` is not defined as a type.
        container_svc: ContainerService,
        task_definition: str,
        mpc_game_svc: MPCGameService,
    ) -> None:
        """Constructor of MPCService
        Keyword arguments:
        container_svc -- service to spawn container instances
        task_definition -- containers task definition
        mpc_game_svc -- service to generate package name and game arguments.
        """
        if container_svc is None or mpc_game_svc is None:
            raise ValueError(
                f"Dependency is missing. container_svc={container_svc}, mpc_game_svc={mpc_game_svc}"
            )

        # pyre-fixme[4]: Attribute must be annotated.
        self.container_svc = container_svc
        self.task_definition = task_definition
        self.mpc_game_svc: MPCGameService = mpc_game_svc
        self.logger: logging.Logger = logging.getLogger(__name__)

        # pyre-fixme[4]: Attribute must be annotated.
        self.onedocker_svc = OneDockerService(self.container_svc, self.task_definition)

    """
    The game_args should be consistent with the game_config, which should be
    defined in caller's game repository.

    For example,
    If the game config looks like this:

    game_config = {
    "game": {
        "onedocker_package_name": "package_name",
        "arguments": [
            {"name": "input_filenames", "required": True},
            {"name": "input_directory", "required": True},
            {"name": "output_filenames", "required": True},
            {"name": "output_directory", "required": True},
            {"name": "concurrency", "required": True},
        ],
    },

    The game args should look like this:
    [
        # 1st container
        {
            "input_filenames": input_path_1,
            "input_directory": input_directory,
            "output_filenames": output_path_1,
            "output_directory": output_directory,
            "concurrency": cocurrency,
        },
        # 2nd container
        {
            "input_filenames": input_path_2,
            "input_directory": input_directory,
            "output_filenames": output_path_2,
            "output_directory": output_directory,
            "concurrency": cocurrency,
        },
    ]
    """

    def convert_cmd_args_list(
        self,
        game_name: str,
        game_args: List[Dict[str, Any]],
        mpc_party: MPCParty,
        server_ips: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        """Convert Game args (MPC) to Cmd args be used by Onedocker service.

        Args:
            game_name: the name of the MPC game to run, e.g. lift
            game_args: arguments that are passed to game binaries by onedocker
            mpc_party: The role played by the MPC instance, e.g. SERVER or CLIENT
            server_ips: ip addresses of the publisher's containers.

        Returns:
            return: Tuple of (binary_name, cmd_args_list - compatible with oneDocker API)
        """
        if not game_args:
            raise ValueError("Missing game_args or it's empty")
        if mpc_party is MPCParty.CLIENT and not server_ips:
            raise ValueError("Missing server_ips")

        cmd_args_list = []
        binary_name = None
        for i in range(len(game_args)):
            game_arg = game_args[i] if game_args is not None else {}
            server_ip = server_ips[i] if server_ips is not None else None
            package_name, cmd_args = self.mpc_game_svc.build_onedocker_args(
                game_name=game_name,
                mpc_party=mpc_party,
                server_ip=server_ip,
                **game_arg,
            )
            if binary_name is None:
                binary_name = package_name

            cmd_args_list.append(cmd_args)

        if binary_name is None:
            raise ValueError("Can't get binary_name from game_args")

        return (binary_name, cmd_args_list)


def map_private_computation_role_to_mpc_party(
    # pyre-fixme[11]: Annotation `PrivateComputationRole` is not defined as a type.
    private_computation_role: PrivateComputationRole,
) -> MPCParty:
    """Convert PrivateComputationRole to MPCParty

    Args:
        pc_role: The role played in the private computation game, e.g. publisher or partner

    Returns:
        The MPCParty that corresponds to the given PrivateComputationRole, e.g. server or client

    Exceptions:
        ValueError: raised when there is no MPCParty associated with private_computation_role
    """
    # pyre-fixme[16]: Module `private_computation` has no attribute `entity`.
    if private_computation_role is PrivateComputationRole.PUBLISHER:
        return MPCParty.SERVER
    # pyre-fixme[16]: Module `private_computation` has no attribute `entity`.
    elif private_computation_role is PrivateComputationRole.PARTNER:
        return MPCParty.CLIENT
    else:
        raise ValueError(f"No mpc party defined for {private_computation_role}")
