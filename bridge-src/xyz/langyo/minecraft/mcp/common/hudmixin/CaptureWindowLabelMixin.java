package xyz.langyo.minecraft.mcp.common.hudmixin;

import xyz.langyo.minecraft.mcp.common.ScenarioActions;

import net.minecraft.class_1041;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

@Mixin(value = class_1041.class, remap = false)
public abstract class CaptureWindowLabelMixin {
    @ModifyVariable(method = "method_24286", at = @At("HEAD"), argsOnly = true, remap = false)
    private String lab$retainCaptureTitle(String requested) {
        return ScenarioActions.retainedCaptureWindowTitle((class_1041) (Object) this, requested);
    }
}
