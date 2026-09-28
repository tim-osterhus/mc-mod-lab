package xyz.langyo.minecraft.mcp.common.hudmixin;

import xyz.langyo.minecraft.mcp.common.HudTraceRecorder;

import net.minecraft.class_310;
import net.minecraft.class_757;
import net.minecraft.class_9779;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = class_757.class, remap = false)
public abstract class HudTraceMixin {
    @Inject(method = "method_3192", at = @At("HEAD"), remap = false)
    private void lab$beginRender(class_9779 delta, boolean renderLevel, CallbackInfo info) {
        HudTraceRecorder.beginRender();
    }

    @Inject(method = "method_3192", at = @At("RETURN"), remap = false)
    private void lab$endRender(class_9779 delta, boolean renderLevel, CallbackInfo info) {
        HudTraceRecorder.endRender(class_310.method_1551(), delta);
    }
}
